"""Same-release Maven publication verification and immediate dependency evidence.

Parent/BOM documents supply declarations and defaults, never transitive library
membership. Profiles, version ranges and unresolved placeholders remain gaps.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from .configuration import expand
from .data import JSON, repo_name, string


def pom_url(coordinate: str, version: str) -> str:
    group, artifact = coordinate.split(":", 1)
    return "https://repo.maven.apache.org/maven2/" + "/".join(
        (group.replace(".", "/"), artifact, version, f"{artifact}-{version}.pom")
    )


def exact_version(value: str) -> bool:
    return bool(
        value
        and not re.search(r"[\[\](),${}+*\s]", value)
        and value.upper() not in ("LATEST", "RELEASE")
    )


@dataclass
class Publication:
    verified: bool = False
    management_incomplete: bool = False
    repositories: set[str] = field(default_factory=set)
    dependencies: list[dict[str, JSON]] = field(default_factory=list)
    properties: dict[str, str] = field(default_factory=dict)
    management: dict[tuple[str, str, str], dict[str, JSON]] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


def resolve_pom(
    coordinate: str,
    version: str,
    fetch: Callable[[str], str],
    trail: tuple[str, ...] = (),
    property_overrides: dict[str, str] | None = None,
) -> Publication:
    result = Publication()
    key = coordinate + "@" + version
    if not re.fullmatch(r"[^:/\s${}]+:[^:/\s${}]+", coordinate):
        result.issues.append("Unresolved POM coordinate: " + key)
        return result
    if key in trail or len(trail) >= 16 or not exact_version(version):
        result.issues.append("Unresolved or cyclic parent/BOM version: " + key)
        return result
    url = pom_url(coordinate, version)
    result.evidence.append(url)
    try:
        root = ET.fromstring(fetch(url))
    except ET.ParseError:
        result.issues.append("POM unavailable or malformed: " + key)
        return result
    for element in root.iter():
        element.tag = element.tag.rsplit("}", 1)[-1]
    if root.tag != "project":
        result.issues.append("Not a Maven project POM: " + key)
        return result
    props = {e.tag: e.text or "" for e in root.findall("./properties/*")}
    props.update(property_overrides or {})

    def subst(value: str) -> str:
        for _ in range(16):
            updated = re.sub(r"\$\{([^}]+)\}", lambda m: props.get(m[1], m[0]), value)
            if updated == value:
                break
            value = updated
        return value

    parent = root.find("parent")
    inherited = Publication()
    if parent is not None:
        parent_name = subst(
            (parent.findtext("groupId") or "") + ":" + (parent.findtext("artifactId") or "")
        )
        parent_version = subst(parent.findtext("version") or "")
        inherited = resolve_pom(parent_name, parent_version, fetch, trail + (key,), props)
        props = inherited.properties | props
        result.management.update(inherited.management)
        result.issues.extend(inherited.issues)
        result.evidence.extend(inherited.evidence)
    group = subst(root.findtext("groupId") or root.findtext("parent/groupId") or "")
    artifact = subst(root.findtext("artifactId") or "")
    own_version = subst(root.findtext("version") or root.findtext("parent/version") or "")
    for name, value in (("groupId", group), ("artifactId", artifact), ("version", own_version)):
        props["project." + name] = value
        props["pom." + name] = value
    if group + ":" + artifact != coordinate or own_version != version:
        result.issues.append("POM identity differs from requested coordinate/version: " + key)
        return result
    result.verified = True
    result.properties = {k: subst(v) for k, v in props.items()}
    if root.find("profiles") is not None:
        result.issues.append("Conditional Maven profiles are not resolved")

    result.repositories = {
        repo_name(subst(e.text or "").replace("git@github.com:", "https://github.com/"))
        for e in root.findall("./scm/*")
    } - {""}
    if root.find("scm") is None:
        result.repositories = set(inherited.repositories)
    # Only unavailable management, not unrelated plugin/profile warnings, taints defaults.
    management_incomplete = parent is not None and (
        not inherited.verified or inherited.management_incomplete
    )

    def identity(dep: dict[str, JSON]) -> tuple[str, str, str]:
        return (
            string(dep["package_name"]),
            string(dep.get("type")) or "jar",
            string(dep.get("classifier")),
        )

    def declaration(dep: ET.Element, defaults: bool = True) -> dict[str, JSON]:
        name = subst((dep.findtext("groupId") or "") + ":" + (dep.findtext("artifactId") or ""))
        kind = subst(dep.findtext("type") or "jar")
        classifier = subst(dep.findtext("classifier") or "")
        managed = result.management.get((name, kind, classifier), {}) if defaults else {}
        version_text = subst(dep.findtext("version") or string(managed.get("requirements")))
        scope = subst(
            dep.findtext("scope")
            or string(managed.get("kind"))
            or ("unknown" if management_incomplete else "compile")
        )
        optional = dep.findtext("optional")
        return {
            "package_name": name,
            "type": kind,
            "classifier": classifier,
            "requirements": version_text,
            "kind": scope,
            "optional": (
                subst(optional) == "true" if subst(optional) in ("true", "false") else None
            )
            if optional is not None
            else managed.get("optional", None if management_incomplete else False),
        }

    local_management = [
        declaration(dep, False)
        for dep in root.findall("./dependencyManagement/dependencies/dependency")
    ]
    imported_management: dict[tuple[str, str, str], dict[str, JSON]] = {}
    for dep in local_management:
        if dep["kind"] == "import":
            imported = resolve_pom(
                string(dep["package_name"]), string(dep["requirements"]), fetch, trail + (key,)
            )
            for name, managed in imported.management.items():
                imported_management.setdefault(name, managed)
            management_incomplete = (
                management_incomplete or not imported.verified or imported.management_incomplete
            )
            result.issues.extend(imported.issues)
            result.evidence.extend(imported.evidence)
    result.management.update(imported_management)
    for dep in local_management:
        if dep["kind"] != "import":
            result.management[identity(dep)] = dep
    direct = {
        identity(dep): dict(dep) for dep in inherited.dependencies if dep.get("kind") != "build"
    }
    for dep in root.findall("./dependencies/dependency"):
        parsed = declaration(dep)
        direct[identity(parsed)] = parsed
    result.management_incomplete = management_incomplete
    result.dependencies = list(direct.values())
    for location, default_group in (
        ("./build/plugins/plugin", "org.apache.maven.plugins"),
        ("./build/extensions/extension", ""),
    ):
        for dep in root.findall(location):
            result.dependencies.append(
                {
                    "package_name": subst(dep.findtext("groupId") or default_group)
                    + ":"
                    + subst(dep.findtext("artifactId") or ""),
                    "requirements": subst(dep.findtext("version") or ""),
                    "kind": "build",
                    "optional": False,
                }
            )
    for dep in result.dependencies:
        if (
            not exact_version(string(dep["requirements"]))
            or "${" in string(dep["package_name"])
            or dep.get("kind") == "unknown"
            or "${" in string(dep.get("kind"))
            or dep.get("optional") is None
        ):
            result.issues.append("Unresolved direct declaration: " + string(dep["package_name"]))
    return result


def matrix_cells(matrix: dict[str, JSON]) -> dict[str, str]:
    """Suffix -> stable cell identity, with plugin suffixes kept intact."""
    cells = {}
    for platform, settings in matrix.items():
        for coordinate in expand(["g:module"], {platform: settings}):
            suffix = coordinate.removeprefix("g:module")
            cells[suffix] = platform + ":" + suffix
    return cells


def memberships(
    coordinate: str, module: str, version: str, publication: Publication, matrix: dict[str, JSON]
) -> set[str]:
    if not publication.verified:
        return set()
    cells = matrix_cells(matrix)
    if coordinate in ("org.scala-lang:scala-library", "org.scala-lang:scala3-library_3"):
        binary = (
            ".".join(version.split(".")[:2])
            if coordinate.endswith(":scala-library") and re.match(r"^2\.\d+\.\d+", version)
            else "3"
            if re.match(r"^3\.\d+\.\d+", version)
            else ""
        )
        return {cells["_" + binary]} if cells.get("_" + binary, "").startswith("jvm:") else set()
    if coordinate != module:
        suffix = coordinate.removeprefix(module)
        return {cells[suffix]} if suffix in cells else set()
    props = publication.properties
    # Legacy sbt publications require both compatibility properties. Presence of
    # plugin metadata prevents a disabled sbt variant leaking into JVM selection.
    if "sbtVersion" in props:
        scala, sbt = props.get("scalaVersion", ""), props["sbtVersion"]
        suffix = ""
        if re.fullmatch(r"2\.12(?:\.\d+)*", scala) and re.fullmatch(r"1\.\d+(?:\.\d+)*", sbt):
            suffix = "_2.12_1.0"
        elif re.fullmatch(r"3(?:\.\d+)*", scala) and re.fullmatch(r"2(?:\.\d+)*", sbt):
            suffix = "_sbt2_3"
        return {cells[suffix]} if suffix in cells else set()
    binaries = set()
    deps = [
        (string(d.get("package_name")), string(d.get("requirements")))
        for d in publication.dependencies
        if d.get("kind") != "build"
    ]
    if coordinate in ("org.scala-lang:scala-library", "org.scala-lang:scala3-library_3"):
        deps = [(coordinate, version)]
    for name, number in deps:
        if name == "org.scala-lang:scala-library" and re.match(r"^2\.\d+\.\d+(?:$|[-+])", number):
            binaries.add(".".join(number.split(".")[:2]))
        if name in ("org.scala-lang:scala3-library_3", "org.scala-lang:scala-library") and re.match(
            r"^3\.\d+\.\d+(?:$|[-+])", number
        ):
            binaries.add("3")
    return {cells["_" + b] for b in binaries if cells.get("_" + b, "").startswith("jvm:")}
