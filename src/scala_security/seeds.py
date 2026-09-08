"""Freeze source-ranked category selections and all published artifact variants."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import yaml
from bs4 import BeautifulSoup

from .configuration import (
    ARTIFACT_CAP,
    ARTIFACT_SELECTION,
    DEFAULT_MATRIX,
    MAX_HOPS,
    modules_for,
    parse_config,
)
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
    candidates: list[dict[str, JSON]], sections: dict[str, list[str]]
) -> list[dict[str, JSON]]:
    """Retain every eligible repository, deduplicated across subsections."""
    chosen: dict[str, dict[str, JSON]] = {}
    for child in dict.fromkeys(c for children in sections.values() for c in children):
        ranked = []
        for project in candidates:
            repo = string(project["repository"])
            ranks = [
                int(str(s["rank"]))
                for s in rows(project.get("selection"))
                if s.get("category") == child
            ]
            if ranks:
                ranked.append((min(ranks), repo, project))
        seen: set[str] = set()
        for _, repo, project in sorted(ranked, key=lambda r: (r[0], r[1])):
            if repo in seen:
                continue
            seen.add(repo)
            if repo not in chosen:
                chosen[repo] = dict(project, categories=[], selected_from=[])
            categories = chosen[repo]["categories"]
            selected = chosen[repo]["selected_from"]
            assert isinstance(categories, list) and isinstance(selected, list)
            categories.append(child)
            selected.append(child)
    return list(chosen.values())


def seed_document(
    projects: list[dict[str, JSON]],
    sections: dict[str, list[str]],
    matrix: dict[str, JSON],
    selected_at: str,
) -> dict[str, JSON]:
    return {
        "schema": 2,
        "universe": "seed",
        "max_hops": MAX_HOPS,
        "max_artifacts_per_project": ARTIFACT_CAP,
        "artifact_selection": ARTIFACT_SELECTION,
        "selected_at": selected_at,
        "source": INDEX + "/awesome",
        "matrix": matrix,
        "selection_policy": {
            "max_projects": None,
            "max_per_subsection": None,
            "rule": "All eligible projects across every Awesome Scala subsection in captured source order, deduplicated by repository. No project or subsection quota.",
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
        while True:
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
