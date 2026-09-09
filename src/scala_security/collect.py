"""Reverse discovery, release filtering and version-specific dependency evidence."""

from __future__ import annotations

import json
import re
import sqlite3
import time
from datetime import datetime, timezone
from urllib.parse import quote
from xml.etree import ElementTree as ET

from .configuration import ARTIFACT_CAP, ARTIFACT_SELECTION, MAX_HOPS, SeedConfig
from .data import JSON, number, obj, repo_name, rows, string
from .http import Fetcher, parallel, query, stream
from .publication import Publication, matrix_cells, memberships, pom_url, resolve_pom
from .seeds import INDEX, coordinates
from .selection import rank_artifacts

BASE = "https://packages.ecosyste.ms/api/v1"
MAVEN = BASE + "/registries/repo1.maven.org/packages/"


def package_url(name: str) -> str:
    return MAVEN + quote(name, safe=":._-")


def exact(requirement: str) -> bool:
    return bool(
        requirement
        and not re.search(r"[\[\](),${}+*\s]", requirement)
        and requirement.upper() not in ("LATEST", "RELEASE")
    )


def pom_dependencies(text: str) -> list[dict[str, JSON]]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    ns = {"m": "http://maven.apache.org/POM/4.0.0"}
    # Maven POMs may omit their namespace.
    for element in root.iter():
        element.tag = element.tag.rsplit("}", 1)[-1]
    del ns
    props = {e.tag: e.text or "" for e in root.findall("./properties/*")}
    for name in ("version", "groupId", "artifactId"):
        val = root.findtext(name) or root.findtext("parent/" + name) or ""
        props["project." + name] = val
        props["pom." + name] = val

    def expand(value: str) -> str:
        for _ in range(10):
            new = re.sub(r"\$\{([^}]+)\}", lambda m: props.get(m[1], m[0]), value)
            if new == value:
                break
            value = new
        return value

    inherited = root.find("parent") is not None or root.find("dependencyManagement") is not None
    result: list[dict[str, JSON]] = []
    for dep in root.findall("./dependencies/dependency"):
        group, artifact = dep.findtext("groupId"), dep.findtext("artifactId")
        if not group or not artifact:
            continue
        opt = dep.findtext("optional")
        scope = dep.findtext("scope")
        result.append(
            {
                "package_name": expand(group + ":" + artifact),
                "requirements": expand(dep.findtext("version") or ""),
                "kind": expand(scope) if scope else None if inherited else "compile",
                "optional": opt == "true" if opt else None if inherited else False,
            }
        )
    # Explicit active build plugins/extensions are build inputs, not runtime dependencies.
    # pluginManagement alone does not activate a plugin.
    for location, default_group in (
        ("./build/plugins/plugin", "org.apache.maven.plugins"),
        ("./build/extensions/extension", ""),
    ):
        for dep in root.findall(location):
            group = dep.findtext("groupId") or default_group
            artifact = dep.findtext("artifactId")
            if group and artifact:
                result.append(
                    {
                        "package_name": expand(group + ":" + artifact),
                        "requirements": expand(dep.findtext("version") or ""),
                        "kind": "build",
                        "optional": False,
                    }
                )
    return result


def dependencies(api: object, pom: str) -> list[dict[str, JSON]]:
    result = [
        dict(d)
        for d in rows(obj(api).get("dependencies"))
        if d.get("ecosystem", "maven") == "maven"
    ]
    for dep in pom_dependencies(pom):
        matches = [d for d in result if d.get("package_name") == dep["package_name"]]
        version_matches = [d for d in matches if d.get("requirements") == dep["requirements"]]
        matches = version_matches or matches
        if len(matches) == 1:
            for key in ("kind", "optional"):
                if dep[key] is not None:
                    matches[0][key] = dep[key]
            if not exact(string(matches[0].get("requirements"))) and exact(
                string(dep["requirements"])
            ):
                matches[0]["requirements"] = dep["requirements"]
        elif not matches:
            result.append(dep)
    return result


def compact_package(package: dict[str, JSON]) -> dict[str, JSON]:
    """Keep only graph/Value inputs in memory; full payload stays in evidence."""
    result = {
        k: package[k]
        for k in (
            "name",
            "repository_url",
            "latest_release_number",
            "latest_release_published_at",
            "registry",
        )
        if k in package
    }
    result["repo_metadata"] = {
        "stargazers_count": obj(package.get("repo_metadata")).get("stargazers_count"),
        "last_synced_at": obj(package.get("repo_metadata")).get("last_synced_at"),
    }
    return result


class Collector:
    def __init__(
        self, db: sqlite3.Connection, fetch: Fetcher, config: SeedConfig | None = None
    ) -> None:
        self.db, self.fetch = db, fetch
        self.config = config
        self.claims: dict[str, set[str]] = {}
        self.unresolved_owners: set[str] = set()

    def gap(self, stage: str, subject: str, reason: str) -> None:
        self.db.execute("INSERT OR IGNORE INTO gaps VALUES(?,?,?)", (stage, subject, reason))

    def package(self, data: dict[str, JSON], project: str = "") -> str:
        name = string(data.get("name"))
        if not name:
            return ""
        project = project or repo_name(data.get("repository_url"))
        if name in self.unresolved_owners:
            project = ""
        if not project and "repository_url" in data:
            self.gap("mapping", name, "No supported GitHub repository URL in package metadata")
        if project:
            stars = number(obj(data.get("repo_metadata")).get("stargazers_count"))
            self.db.execute(
                "INSERT OR IGNORE INTO projects(id,stars) VALUES(?,?)", (project, stars)
            )
            observed = string(obj(data.get("repo_metadata")).get("last_synced_at"))
            if stars is not None:
                self.db.execute(
                    """UPDATE projects SET stars=?,stars_observed=?,source=? WHERE id=?
                    AND (stars_observed IS NULL OR stars_observed<? OR
                    (stars_observed=? AND (stars IS NULL OR stars<?)))""",
                    (stars, observed, package_url(name), project, observed, observed, stars),
                )
        self.db.execute(
            """INSERT INTO artifacts(id,project,latest,published,source) VALUES(?,?,?,?,?)
          ON CONFLICT(id) DO UPDATE SET project=coalesce(artifacts.project,excluded.project),
          latest=coalesce(excluded.latest,artifacts.latest),published=coalesce(excluded.published,artifacts.published)""",
            (
                name,
                project or None,
                data.get("latest_release_number"),
                data.get("latest_release_published_at"),
                package_url(name),
            ),
        )
        return name

    def seed(self, item: dict[str, JSON]) -> list[str]:
        if self.config is None:
            raise ValueError("A validated seed matrix is required for collection")
        project = string(item["repository"])
        self.db.execute(
            "INSERT OR IGNORE INTO projects(id,seed,categories) VALUES(?,1,?)",
            (project, json.dumps(item["categories"])),
        )
        self.db.execute("UPDATE projects SET seed=1 WHERE id=?", (project,))
        _, latest, packages = self.release(project)
        for package in packages:
            self.package(package, project)
        releases = {string(r.get("version")) for r in latest}
        if len(releases) != 1 or not next(iter(releases), ""):
            self.gap("release", project, "Missing or ambiguous project latest release")
        version = next(iter(releases)) if len(releases) == 1 else ""
        self.db.execute("UPDATE projects SET latest=? WHERE id=?", (version or None, project))
        inventory = self.fetch.json(
            f"{INDEX}/api/v1/projects/{project}/artifacts?stable-only=false"
        )
        reported = set(coordinates(inventory)) | set(coordinates(latest))
        if not isinstance(inventory, list):
            self.gap(
                "inventory", project, "Scaladex inventory unavailable; POM verification required"
            )
        expected = self.config.coordinates(item)
        modules = [string(m) for m in item["modules"]] if isinstance(item["modules"], list) else []
        candidates = (set(expected) & reported) | set(modules)
        cell_membership: dict[str, set[str]] = {}

        def verify(name: str):
            discovery_version = version
            publication = resolve_pom(name, version, self.fetch.text)
            # Only observed unsuffixed coordinates may use an older publication
            # for target classification. Never substitute it as a consumer root.
            if name in modules and name in reported and not publication.verified:
                raw = obj(self.fetch.json(package_url(name)))
                historical = string(raw.get("latest_release_number"))
                if exact(historical) and historical != version:
                    discovery_version = historical
                    publication = resolve_pom(name, historical, self.fetch.text)
            return name, discovery_version, publication

        for name, discovery_version, publication in parallel(verify, sorted(candidates)):
            module = (
                name
                if name in modules
                else next(m for m in sorted(modules, key=len, reverse=True) if name.startswith(m))
            )
            cells = memberships(name, module, discovery_version, publication, self.config.matrix)
            # Inventory establishes suffixed coordinate existence independently of
            # the latest project release. Exact reached versions are verified later.
            if name != module and name in reported:
                suffix = name.removeprefix(module)
                cell = matrix_cells(self.config.matrix).get(suffix)
                if cell:
                    cells = {cell}
            issues = list(publication.issues)
            if publication.verified and name not in set(coordinates(latest)):
                issues.append(
                    "Verified exact POM coordinate absent from Scaladex chosen-release records"
                )
            if publication.verified and not cells:
                issues.append("Unknown or disabled matrix membership; no enabled cell established")
            self.db.execute(
                "INSERT OR REPLACE INTO publications VALUES(?,?,?,?,?,?,?,?)",
                (
                    project,
                    name,
                    discovery_version,
                    int(publication.verified),
                    json.dumps(sorted(cells)),
                    json.dumps(publication.dependencies),
                    json.dumps(issues),
                    json.dumps(publication.evidence),
                ),
            )
            self.db.execute(
                "INSERT OR REPLACE INTO coordinate_checks VALUES(?,?,?)",
                (project, name, int(publication.verified)),
            )
            for issue in issues:
                self.gap("publication", name + "@" + version, issue)
            if cells:
                cell_membership[name] = cells
        artifacts = sorted(cell_membership)
        if not artifacts:
            self.gap(
                "release",
                project,
                "No inventory or verified publication coordinates match enabled matrix cells",
            )
        counts: dict[str, int] = {}
        ranking_url = query(
            BASE + "/packages/lookup",
            repository_url="https://github.com/" + project,
            sort="dependent_packages_count",
            order="desc",
        )
        if len(artifacts) > ARTIFACT_CAP:
            for record in self.fetch.pages(ranking_url):
                name = string(record.get("name"))
                raw = record.get("dependent_packages_count")
                if obj(record.get("registry")).get("name") != "repo1.maven.org":
                    continue
                if (
                    name in artifacts
                    and isinstance(raw, int)
                    and not isinstance(raw, bool)
                    and raw >= 0
                ):
                    counts[name] = max(counts.get(name, 0), raw)
            missing = set(artifacts) - counts.keys()
            if missing:
                self.gap(
                    "artifact_selection",
                    project,
                    f"{len(missing)} candidate counts unknown; sorted after known counts",
                )
        ranked = rank_artifacts(cell_membership, counts, ARTIFACT_CAP)
        self.db.executemany(
            "INSERT OR REPLACE INTO artifact_selection VALUES(?,?,?,?,?,?,?)",
            [
                (
                    project,
                    name,
                    counts.get(name),
                    int(i < ARTIFACT_CAP),
                    i + 1,
                    ranking_url if len(artifacts) > ARTIFACT_CAP else None,
                    ARTIFACT_SELECTION
                    if len(artifacts) > ARTIFACT_CAP
                    else "All verified candidates fit; ranking metadata not requested",
                )
                for i, name in enumerate(ranked)
            ],
        )
        artifacts = ranked[:ARTIFACT_CAP]
        for name in artifacts:
            self.claims.setdefault(name, set()).add(project)
            self.package({"name": name}, project)
            self.db.execute("INSERT OR IGNORE INTO target_artifacts VALUES(?)", (name,))
        return artifacts

    def reconcile_ownership(self) -> None:
        ambiguous = [name for name, owners in self.claims.items() if len(owners) > 1]
        for name, raw in parallel(
            lambda name: (name, obj(self.fetch.json(package_url(name)))), ambiguous
        ):
            owner = repo_name(raw.get("repository_url"))
            if owner not in self.claims[name]:
                owner = ""
                self.unresolved_owners.add(name)
            self.db.execute("UPDATE artifacts SET project=? WHERE id=?", (owner or None, name))
            self.gap(
                "ownership",
                name,
                "Multiple Scaladex claims; "
                + (
                    "assigned from package repository metadata to " + owner
                    if owner
                    else "unresolved; excluded from project attribution"
                ),
            )

    def discover(self, targets: list[str]) -> set[str]:
        frontier, visited, possible = set(targets), set(), set()
        for depth in range(3):
            pending = sorted(frontier - visited)
            visited.update(pending)
            frontier = set()
            # Historical intermediate relationships are necessary when current consumers use older releases.
            latest = "true" if depth == 2 else "false"

            def reverse(name: str) -> tuple[str, list[dict[str, JSON]]]:
                return name, self.fetch.pages(
                    query(package_url(name) + "/dependent_packages", latest=latest), compact_package
                )

            for count, (target, dependants) in enumerate(stream(reverse, pending), 1):
                for package in dependants:
                    name = self.package(package)
                    if name:
                        possible.add(name)
                        frontier.add(name)
                if count % 120 == 0 or count == len(pending):
                    self.db.commit()
                    print(
                        f"Reverse hop {depth + 1}: {count}/{len(pending)} artifacts; {len(possible)} discovered",
                        flush=True,
                    )
        return visited | possible

    def release(self, project: str) -> tuple[str, list[dict[str, JSON]], list[dict[str, JSON]]]:
        latest = rows(self.fetch.json(f"{INDEX}/api/v1/projects/{project}/versions/latest"))
        if latest:
            return project, latest, []
        # Java consumers and missing Scaladex entries: reconcile all repo-linked Maven artifacts.
        packages = self.fetch.pages(
            query(BASE + "/packages/lookup", repository_url="https://github.com/" + project),
            compact_package,
        )
        packages = [
            p
            for p in packages
            if obj(p.get("registry")).get("name", "repo1.maven.org") == "repo1.maven.org"
        ]
        dated = [
            p
            for p in packages
            if p.get("latest_release_published_at") and p.get("latest_release_number")
        ]
        if not dated:
            return project, [], packages
        newest = max(dated, key=lambda p: string(p["latest_release_published_at"]))
        version = newest["latest_release_number"]
        selected = [
            {"name": p["name"], "version": version}
            for p in packages
            if p.get("latest_release_number") == version
        ]
        return project, selected, packages

    def roots(self) -> list[str]:
        if self.config is not None:
            roots = []
            for row in self.db.execute(
                "SELECT DISTINCT a.artifact,p.latest FROM artifact_selection a JOIN projects p ON p.id=a.project WHERE a.selected=1 AND p.latest IS NOT NULL ORDER BY a.artifact,p.latest"
            ):
                key = row[0] + "@" + row[1]
                self.db.execute(
                    "INSERT OR IGNORE INTO versions(id,artifact,number) VALUES(?,?,?)",
                    (key, row[0], row[1]),
                )
                roots.append(key)
            self.db.commit()
            return roots

        projects = [
            r[0] for r in self.db.execute("SELECT id FROM projects WHERE seed=1 ORDER BY id")
        ]
        roots: list[str] = []
        for start in range(0, len(projects), 120):
            for project, latest, packages in parallel(self.release, projects[start : start + 120]):
                for package in packages:
                    self.package(package, project)
                if not latest:
                    self.gap(
                        "release",
                        project,
                        "Project latest release unavailable; excluded from dependant qualification",
                    )
                    continue
                versions = {string(x.get("version")) for x in latest}
                if len(versions) != 1:
                    self.gap("release", project, "Ambiguous project release; excluded")
                    continue
                version = next(iter(versions))
                self.db.execute(
                    "UPDATE projects SET latest=? WHERE id=?", (version or None, project)
                )
                seed_project = self.db.execute(
                    "SELECT seed FROM projects WHERE id=?", (project,)
                ).fetchone()[0]
                roots_before = len(roots)
                for record in latest:
                    name = (
                        string(record.get("name"))
                        or f"{record.get('groupId')}:{record.get('artifactId')}"
                    )
                    if (
                        seed_project
                        and not self.db.execute(
                            "SELECT 1 FROM target_artifacts t JOIN artifacts a ON a.id=t.artifact WHERE t.artifact=? AND a.project=?",
                            (name, project),
                        ).fetchone()
                    ):
                        continue
                    self.package({"name": name}, project)
                    root = name + "@" + version
                    self.db.execute(
                        "INSERT OR IGNORE INTO versions(id,artifact,number) VALUES(?,?,?)",
                        (root, name, version),
                    )
                    roots.append(root)
                if seed_project and len(roots) == roots_before:
                    self.gap(
                        "release",
                        project,
                        "Latest project release has no selected matrix coordinates; no older seed release substituted",
                    )
            self.db.commit()
            print(
                f"Latest releases: {min(start + 120, len(projects))}/{len(projects)} projects",
                flush=True,
            )
        return roots

    def publication_owner(self, name: str, publication: Publication) -> tuple[str, str, list[str]]:
        evidence = list(publication.evidence)
        owners = set(publication.repositories) if publication.verified else set()
        if not owners:
            url = package_url(name)
            raw = obj(self.fetch.json(url))
            owner = repo_name(raw.get("repository_url"))
            owners = {owner} if owner else set()
            evidence.append(url)
        seeds = {string(p["repository"]) for p in self.config.projects} if self.config else set()
        canonical = set()
        for owner in owners:
            if owner not in seeds:
                url = "https://api.github.com/repos/" + owner
                raw = obj(self.fetch.json(url))
                owner = string(raw.get("full_name")).lower() or owner
                evidence.append(url)
            canonical.add(owner)
        owner = next(iter(canonical)) if len(canonical) == 1 else ""
        return owner, ("resolved" if owner else "conflict" if canonical else "unknown"), evidence

    def version(
        self, key: str
    ) -> tuple[str, list[dict[str, JSON]], str, bool, bool, list[str], tuple[str, str, list[str]]]:
        name, version = key.rsplit("@", 1)
        url = pom_url(name, version)
        api_url = package_url(name) + "/versions/" + quote(version, safe="")
        data = self.fetch.json(api_url)
        publication = resolve_pom(name, version, self.fetch.text)
        deps = publication.dependencies if publication.verified else dependencies(data, "")
        usable = publication.verified or isinstance(obj(data).get("dependencies"), list)
        issues = list(publication.issues)
        for dep in deps:
            if (
                not exact(string(dep.get("requirements")))
                or dep.get("kind")
                not in {
                    "compile",
                    "runtime",
                    "test",
                    "provided",
                    "build",
                    "development",
                    "system",
                    "import",
                }
                or dep.get("optional") is None
            ):
                issues.append("Unresolved direct dependency: " + string(dep.get("package_name")))
        resolved = [
            d
            for d in deps
            if exact(string(d.get("requirements")))
            and d.get("kind")
            in {
                "compile",
                "runtime",
                "test",
                "provided",
                "build",
                "development",
                "system",
                "import",
            }
            and re.fullmatch(r"[^:\s${}]+:[^:\s${}]+", string(d.get("package_name")))
        ]
        usable = usable and (bool(resolved) or (not deps and not issues))
        return (
            key,
            deps,
            url if publication.verified else api_url,
            bool(publication.verified or data),
            usable,
            issues,
            self.publication_owner(name, publication),
        )

    def forward(self, roots: list[str], relevant: set[str]) -> None:
        frontier = set(roots)
        visited: set[str] = set()
        for depth in range(MAX_HOPS):
            pending = sorted(frontier - visited)
            visited.update(pending)
            frontier = set()
            for start in range(0, len(pending), 120):
                for key, deps, evidence, available, usable, issues, ownership in parallel(
                    self.version, pending[start : start + 120]
                ):
                    self.db.execute(
                        "UPDATE versions SET fetched=? WHERE id=?", (int(available), key)
                    )
                    self.db.execute(
                        "INSERT OR REPLACE INTO version_coverage VALUES(?,?,?,?)",
                        (key, int(usable), int(usable and not issues), json.dumps(issues)),
                    )
                    self.db.execute(
                        "INSERT OR REPLACE INTO version_ownership VALUES(?,?,?,?)",
                        (key, ownership[0] or None, ownership[1], json.dumps(ownership[2])),
                    )
                    if ownership[1] != "resolved":
                        self.gap("ownership", key, "Publication owner " + ownership[1])
                    for issue in issues:
                        self.gap("dependency_evidence", key, issue)
                    if not available:
                        self.gap("version", key, "Neither version API nor POM available")
                    for dep in deps:
                        name, requirement = (
                            string(dep.get("package_name")),
                            string(dep.get("requirements")),
                        )
                        if not name or ":" not in name or name not in relevant:
                            continue
                        self.package({"name": name})
                        target = name + "@" + requirement
                        scope = string(dep.get("kind")) or "unknown"
                        optional = (
                            dep.get("optional") if isinstance(dep.get("optional"), bool) else None
                        )
                        is_exact = exact(requirement)
                        self.db.execute(
                            "INSERT OR IGNORE INTO versions(id,artifact,number) VALUES(?,?,?)",
                            (target, name, requirement),
                        )
                        self.db.execute(
                            "INSERT OR IGNORE INTO edges(source,target,scope,optional,exact,evidence) VALUES(?,?,?,?,?,?)",
                            (key, target, scope, optional, int(is_exact), evidence),
                        )
                        if not is_exact or scope == "unknown" or optional is None:
                            self.gap(
                                "declaration",
                                key + " -> " + target,
                                "Unresolved version, scope or optionality",
                            )
                        scopes = {"compile", "runtime"} | (
                            {"test", "provided", "build", "development"} if depth == 0 else set()
                        )
                        if (
                            depth < MAX_HOPS - 1
                            and name in relevant
                            and is_exact
                            and (depth == 0 or optional is False)
                            and scope in scopes
                        ):
                            frontier.add(target)
                self.db.commit()
                print(
                    f"Forward hop {depth + 1}: {min(start + 120, len(pending))}/{len(pending)} versions",
                    flush=True,
                )

        # Terminal hop nodes also need exact-version ownership even though their
        # outgoing dependencies are beyond the traversal horizon.
        pending = [
            r[0]
            for r in self.db.execute(
                "SELECT v.id FROM versions v LEFT JOIN version_ownership o ON o.version=v.id WHERE o.version IS NULL AND EXISTS (SELECT 1 FROM edges e WHERE e.target=v.id)"
            )
            if exact(r[0].rsplit("@", 1)[1])
        ]

        def terminal_owner(key: str):
            name, version = key.rsplit("@", 1)
            pub = resolve_pom(name, version, self.fetch.text)
            return key, self.publication_owner(name, pub)

        for key, ownership in parallel(terminal_owner, pending):
            self.db.execute(
                "INSERT OR REPLACE INTO version_ownership VALUES(?,?,?,?)",
                (key, ownership[0] or None, ownership[1], json.dumps(ownership[2])),
            )
        self.db.commit()

    def enrich(self) -> None:
        projects = [r[0] for r in self.db.execute("SELECT id FROM projects WHERE seed=1")]

        def evidence(project: str) -> tuple[str, dict[str, tuple[str, dict[str, JSON]]]]:
            enc = quote(project, safe="")
            urls = {
                "repository": f"https://repos.ecosyste.ms/api/v1/hosts/GitHub/repositories/{enc}",
                "commits": f"https://commits.ecosyste.ms/api/v1/hosts/GitHub/repositories/{enc}",
                "scorecard": f"https://api.securityscorecards.dev/projects/github.com/{project}",
            }
            keep = {
                "repository": (
                    "pushed_at",
                    "archived",
                    "last_synced_at",
                    "stargazers_count",
                    "language",
                ),
                "commits": ("past_year_committers", "last_synced_at"),
                "scorecard": ("checks", "date", "repo"),
            }
            result = {}
            for kind, url in urls.items():
                raw = obj(self.fetch.json(url))
                result[kind] = (url, {k: raw[k] for k in keep[kind] if k in raw})
            return project, result

        for project, items in parallel(evidence, projects):
            for kind, (url, payload) in items.items():
                self.db.execute(
                    "INSERT OR REPLACE INTO observations VALUES(?,?,?,?)",
                    (project, kind, json.dumps(payload), url),
                )
                if kind == "repository":
                    self.db.execute(
                        "UPDATE projects SET stars=coalesce(?,stars) WHERE id=?",
                        (payload.get("stargazers_count"), project),
                    )
        self.db.commit()

    def timing(self, key: str, start: float) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO metadata VALUES(?,?)",
            (key, str(time.monotonic() - start)),
        )
        self.db.commit()

    def run(self, seeds: list[dict[str, JSON]]) -> None:
        if self.config is None or seeds != self.config.projects:
            raise ValueError(
                "Collection requires the validated configuration and its seed projects"
            )
        self.db.execute("INSERT OR REPLACE INTO metadata VALUES('seed_schema','2')")
        self.db.execute(
            "INSERT OR REPLACE INTO metadata VALUES(?,?)",
            ("target_matrix", json.dumps(self.config.matrix)),
        )
        self.db.execute("INSERT OR REPLACE INTO metadata VALUES('universe','seed')")
        self.db.execute(
            "INSERT OR REPLACE INTO metadata VALUES(?,?)",
            ("max_artifacts_per_project", str(ARTIFACT_CAP)),
        )
        self.db.execute(
            "INSERT OR REPLACE INTO metadata VALUES(?,?)",
            ("artifact_selection", ARTIFACT_SELECTION),
        )
        self.db.execute("INSERT OR REPLACE INTO metadata VALUES(?,?)", ("max_hops", str(MAX_HOPS)))
        start = time.monotonic()
        targets: list[str] = []
        for index, seed in enumerate(seeds, 1):
            targets.extend(self.seed(seed))
            self.db.commit()
            print(
                f"Publication selection: {index}/{len(seeds)} projects, {len(targets)} artifacts",
                flush=True,
            )
        print(f"{len(seeds)} seed projects, {len(targets)} target artifacts", flush=True)
        self.db.execute(
            "INSERT OR REPLACE INTO metadata VALUES('ownership_policy','publication-v1')"
        )
        relevant = set(targets)
        phase_start = time.monotonic()
        roots = self.roots()
        self.timing("release_resolution_seconds", phase_start)
        phase_start = time.monotonic()
        self.forward(roots, relevant)
        self.timing("forward_collection_seconds", phase_start)
        phase_start = time.monotonic()
        self.enrich()
        self.timing("health_collection_seconds", phase_start)
        for url, reason in self.fetch.failures:
            self.gap("fetch", url, reason)
        for url in sorted(self.fetch.used):
            record = self.fetch.record(url)
            self.db.execute(
                "INSERT OR REPLACE INTO requests VALUES(?,?,?,?)",
                (url, str(self.fetch.path(url)), record.get("status"), record.get("retrieved_at")),
            )
        self.db.execute(
            "INSERT OR REPLACE INTO metadata VALUES(?,?)",
            ("collection_seconds", str(time.monotonic() - start)),
        )
        self.db.execute(
            "INSERT OR REPLACE INTO metadata VALUES(?,?)",
            ("collected_at", datetime.now(timezone.utc).isoformat()),
        )
        self.db.commit()
