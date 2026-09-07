"""Validated compact seeds and deterministic cross-build expansion."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .data import JSON, obj, rows

SUFFIX = re.compile(r"(?:_(?:sjs|native)[^_]+)?_(?:2\.1[0-3]|3)$")
EXCLUDED_REPOSITORIES = {"com-lihaoyi/mill"}
ZIO_REPOSITORY = re.compile(r"(?:^|[/_.-])zio(?:$|[/_.-])", re.IGNORECASE)


def excluded_repository(repo: str) -> bool:
    return repo.lower() in EXCLUDED_REPOSITORIES or bool(ZIO_REPOSITORY.search(repo))


DEFAULT_MATRIX: dict[str, JSON] = {"jvm": {"scala": ["2.13", "3"]}}


@dataclass(frozen=True)
class SeedConfig:
    matrix: dict[str, JSON]
    projects: list[dict[str, JSON]]

    @property
    def module_count(self) -> int:
        return sum(len(module_names(project)) for project in self.projects)

    def coordinates(self, project: dict[str, JSON]) -> list[str]:
        return expand(project["modules"], self.matrix)


def module_names(project: dict[str, JSON]) -> list[str]:
    raw = project.get("modules")
    if not isinstance(raw, list) or not all(isinstance(m, str) for m in raw):
        raise ValueError("Modules must be a list of coordinate strings")
    return [str(m) for m in raw]


def expand(modules: object, matrix: dict[str, JSON]) -> list[str]:
    result = set()
    if not isinstance(modules, list):
        raise ValueError("modules must be a list")
    for module in modules:
        if not isinstance(module, str) or not re.fullmatch(r"[^:\s]+:[^:\s]+", module):
            raise ValueError("Each module must be groupId:moduleName")
        if SUFFIX.search(module) or re.search(r"_(?:sjs|native)[^_]+(?:_|$)", module):
            raise ValueError(f"Module contains a cross-build suffix: {module}")
        for platform, raw in matrix.items():
            settings = obj(raw)
            expected_keys = {"scala"} if platform == "jvm" else {"scala", "versions"}
            if set(settings) != expected_keys:
                raise ValueError(f"Invalid settings for matrix.{platform}")
            scala = settings.get("scala")
            if not isinstance(scala, list) or not scala:
                raise ValueError(f"matrix.{platform}.scala must be a nonempty list")
            versions = [""] if platform == "jvm" else settings.get("versions")
            if not isinstance(versions, list) or not versions:
                raise ValueError(f"matrix.{platform}.versions must be a nonempty list")
            for version in versions:
                if not isinstance(version, str) or (
                    platform != "jvm" and not re.fullmatch(r"\d+(?:\.\d+)*", version)
                ):
                    raise ValueError("Platform versions must be quoted numeric strings")
                prefix = {"jvm": "", "scala_js": "_sjs", "scala_native": "_native"}.get(platform)
                if prefix is None:
                    raise ValueError(f"Unsupported platform: {platform}")
                for binary in scala:
                    if not isinstance(binary, str) or not re.fullmatch(r"2\.\d+|3", binary):
                        raise ValueError(
                            "Scala binary versions must be quoted strings, such as '2.13' or '3'"
                        )
                    result.add(module + prefix + version + "_" + binary)
    return sorted(result)


def modules_for(artifacts: list[str], matrix: dict[str, JSON]) -> list[str]:
    """Retain only module families with an observed coordinate in this matrix."""
    suffixes = [
        name.removeprefix("validation:module") for name in expand(["validation:module"], matrix)
    ]
    return sorted(
        {
            a[: -len(suffix)]
            for a in artifacts
            for suffix in suffixes
            if a.endswith(suffix) and not re.search(r"_(?:sjs|native)[^_]+$", a[: -len(suffix)])
        }
    )


def parse_config(raw: object) -> SeedConfig:
    data = obj(raw)
    if data.get("schema") != 2:
        raise ValueError("Expected seed schema 2 with a shared matrix and unsuffixed modules")
    matrix = obj(data.get("matrix"))
    if not matrix:
        raise ValueError("A nonempty seed-wide matrix is required")
    expand(["validation:module"], matrix)
    projects = rows(data.get("projects"))
    if not projects or len(projects) > 100:
        raise ValueError("Seeds must contain between 1 and 100 projects")
    raw_projects = data.get("projects")
    if not isinstance(raw_projects, list) or len(projects) != len(raw_projects):
        raise ValueError("Every project must be a mapping")
    seen: set[str] = set()
    allocations: dict[str, int] = {}
    for project in projects:
        repo = project.get("repository")
        if not isinstance(repo, str) or not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
            raise ValueError("Each project requires an owner/repository")
        if excluded_repository(repo):
            raise ValueError(f"Repository excluded by pilot policy: {repo}")
        if repo.lower() in seen:
            raise ValueError(f"Duplicate repository: {repo}")
        seen.add(repo.lower())
        if "artifacts" in project:
            raise ValueError("Expanded artifact lists are not allowed in seed schema 2")
        if not project.get("modules") or not expand(project["modules"], matrix):
            raise ValueError(f"No modules configured for {repo}")
        if not isinstance(project.get("categories"), list) or not project["categories"]:
            raise ValueError(f"Main-section categories required for {repo}")
        section = project.get("selected_from")
        if isinstance(section, str):
            allocations[section] = allocations.get(section, 0) + 1
            if allocations[section] > 10:
                raise ValueError(f"More than ten projects allocated to main section: {section}")
        modules = module_names(project)
        if len(set(modules)) != len(modules):
            raise ValueError(f"Duplicate modules for {repo}")
    return SeedConfig(matrix, projects)
