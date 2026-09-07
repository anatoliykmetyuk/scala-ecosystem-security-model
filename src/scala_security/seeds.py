"""Freeze source-ranked category selections and all published artifact variants."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import yaml
from bs4 import BeautifulSoup

from .configuration import DEFAULT_MATRIX, excluded_repository, modules_for, parse_config
from .data import JSON, obj, rows, string
from .http import Fetcher, parallel

INDEX = "https://index.scala-lang.org"


def coordinates(items: object) -> list[str]:
    return sorted(
        {
            f"{x['groupId']}:{x['artifactId']}"
            for x in rows(items)
            if x.get("groupId") and x.get("artifactId")
        }
    )


def project_inventory(fetch: Fetcher, project: str) -> tuple[list[str], list[dict[str, JSON]]]:
    base = f"{INDEX}/api/v1/projects/{project}"
    artifacts = coordinates(fetch.json(base + "/artifacts?stable-only=false"))
    latest = rows(fetch.json(base + "/versions/latest"))
    return artifacts, latest


def main_sections(html: str) -> dict[str, list[str]]:
    """Keep the overview's section hierarchy, not a flat quota per child category."""
    groups: dict[str, list[str]] = {}
    current = ""
    for heading in BeautifulSoup(html, "html.parser").select("h2,h3"):
        if heading.name == "h2":
            current = heading.get_text(" ", strip=True)
        elif current:
            link = heading.select_one('a[href^="/awesome/"]')
            if link:
                slug = string(link.get("href")).split("/")[-1].split("?")[0]
                if slug not in groups.setdefault(current, []):
                    groups[current].append(slug)
    if not groups:
        raise ValueError("No main Awesome Scala sections found; refusing a flat-category fallback")
    return groups


def choose_projects(
    candidates: list[dict[str, JSON]], sections: dict[str, list[str]], limit: int = 100
) -> list[dict[str, JSON]]:
    """Round-robin sections, then source-ranked child categories, with explicit caps."""
    if not 1 <= limit <= 100:
        raise ValueError("Project limit must be between 1 and 100")
    candidates = [p for p in candidates if not excluded_repository(string(p["repository"]))]
    queues: dict[str, list[dict[str, JSON]]] = {}
    for section, children in sections.items():
        child_queues = []
        for child in children:
            ranked = []
            for project in candidates:
                ranks = [
                    int(str(s["rank"]))
                    for s in rows(project.get("selection"))
                    if s.get("category") == child
                ]
                if ranks:
                    ranked.append((min(ranks), string(project["repository"]), project))
            child_queues.append([p for _, _, p in sorted(ranked, key=lambda r: (r[0], r[1]))])
        queues[section] = [
            q[i]
            for i in range(max(map(len, child_queues), default=0))
            for q in child_queues
            if i < len(q)
        ]
    chosen: list[dict[str, JSON]] = []
    seen: set[str] = set()
    quotas = dict.fromkeys(sections, 0)
    while len(chosen) < limit:
        progress = False
        for section, queue in queues.items():
            if quotas[section] >= 10:
                continue
            while queue and string(queue[0]["repository"]) in seen:
                queue.pop(0)
            if not queue:
                continue
            project = dict(queue.pop(0))
            repo = string(project["repository"])
            seen.add(repo)
            children = {string(s.get("category")) for s in rows(project.get("selection"))}
            project["categories"] = [
                name for name, subs in sections.items() if children.intersection(subs)
            ]
            project["selected_from"] = section
            chosen.append(project)
            quotas[section] += 1
            progress = True
            if len(chosen) == limit:
                break
        if not progress:
            break
    return chosen


def seed_document(
    projects: list[dict[str, JSON]],
    sections: dict[str, list[str]],
    matrix: dict[str, JSON],
    selected_at: str,
) -> dict[str, JSON]:
    return {
        "schema": 2,
        "universe": "seed",
        "max_artifacts_per_project": 20,
        "artifact_selection": "First 20 expanded coordinates in lexicographic order before availability checks; no backfill.",
        "selected_at": selected_at,
        "source": INDEX + "/awesome",
        "matrix": matrix,
        "selection_policy": {
            "max_projects": 100,
            "max_per_main_section": 10,
            "rule": "Round-robin main sections in overview order; within each section, interleave child-category lists in overview order by source rank; skip duplicate repositories; stop at 100 projects or exhaustion. Candidate pool is up to 10 eligible entries per child category.",
            "sections": [{"name": name, "subcategories": subs} for name, subs in sections.items()],
        },
        "projects": projects,
    }


def select(fetch: Fetcher, destination: Path) -> None:
    sections = main_sections(fetch.text(INDEX + "/awesome"))
    categories = list(dict.fromkeys(child for children in sections.values() for child in children))
    matrix = (
        parse_config(yaml.safe_load(destination.read_text())).matrix
        if destination.exists()
        else DEFAULT_MATRIX
    )
    projects: dict[str, dict[str, JSON]] = {}
    exclusions: list[dict[str, JSON]] = []
    inventory: dict[str, tuple[list[str], list[dict[str, JSON]]]] = {}
    languages: dict[str, dict[str, JSON]] = {}
    for category in categories:
        count, page = 0, 1
        seen: set[str] = set()
        while count < 10:
            url = f"{INDEX}/awesome/{category}?page={page}"
            text = fetch.text(url)
            if not text:
                raise RuntimeError(f"Cannot freeze incomplete category {category}")
            doc = BeautifulSoup(text, "html.parser")
            refs = [
                string(a.get("href")).strip("/").lower()
                for a in doc.select("ol.list-result > li > a")
            ]
            refs = [r for r in refs if r not in seen]
            page_refs = refs
            refs = [r for r in refs if not excluded_repository(r)]
            if not page_refs:
                break
            seen.update(page_refs)
            missing = [r for r in refs if r not in inventory]
            for ref, result in parallel(lambda r: (r, project_inventory(fetch, r)), missing):
                inventory[ref] = result
            language_refs = [r for r in refs if r not in languages]
            for ref, data in parallel(
                lambda r: (r, obj(fetch.json(f"https://api.github.com/repos/{r}/languages"))),
                language_refs,
            ):
                languages[ref] = data
            ranks = {ref: rank for rank, ref in enumerate(page_refs, (page - 1) * 20 + 1)}
            for ref in refs:
                rank = ranks[ref]
                artifacts, latest = inventory[ref]
                modules = modules_for(artifacts, matrix)
                language = languages[ref]
                numeric_languages = {
                    k: v for k, v in language.items() if isinstance(v, (int, float))
                }
                primary = (
                    max(numeric_languages, key=lambda k: numeric_languages[k])
                    if numeric_languages
                    else "unknown"
                )
                if not modules or not latest or primary != "Scala":
                    exclusions.append(
                        {
                            "project": ref,
                            "category": category,
                            "reason": "Missing Scala publication/latest release evidence, or Scala is not the largest source language",
                        }
                    )
                    continue
                count += 1
                if ref not in projects:
                    projects[ref] = {
                        "repository": ref,
                        "categories": [],
                        "selection": [],
                        "eligibility": "Scaladex project mapping, published Scala cross-build artifacts, and Scala as largest source language",
                        "modules": modules,
                        "language_evidence": language,
                        "language_source": f"https://api.github.com/repos/{ref}/languages",
                    }
                cats = projects[ref]["categories"]
                selections = projects[ref]["selection"]
                assert isinstance(cats, list) and isinstance(selections, list)
                cats.append(category)
                selections.append({"category": category, "rank": rank, "source": url})
                if count == 10:
                    break
            page += 1
        print(f"Seeds: {category}: {count} eligible; {len(projects)} unique projects", flush=True)
    if fetch.failures:
        raise RuntimeError(
            "Seed source requests failed; refusing to replace the frozen cohort with incomplete evidence"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    document = seed_document(
        choose_projects(list(projects.values()), sections),
        sections,
        matrix,
        datetime.now(timezone.utc).isoformat(),
    )
    document["exclusions"] = exclusions
    parse_config(document)
    destination.write_text(yaml.safe_dump(document, sort_keys=False))
    (destination.parent / "selection-evidence.json").write_text(
        json.dumps({"requests": sorted(fetch.used), "failures": fetch.failures}, indent=2)
    )
