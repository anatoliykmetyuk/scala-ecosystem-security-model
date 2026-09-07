"""Freeze source-ranked category selections and all published artifact variants."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml
from bs4 import BeautifulSoup

from .data import JSON, obj, rows, string
from .http import Fetcher, parallel

INDEX = "https://index.scala-lang.org"
SCALA_SUFFIX = re.compile(r"_(?:2\.\d+|3)(?:[._-].*)?$")


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


def select(fetch: Fetcher, destination: Path) -> None:
    soup = BeautifulSoup(fetch.text(INDEX + "/awesome"), "html.parser")
    categories = sorted(
        {
            string(a.get("href")).split("/")[-1].split("?")[0]
            for a in soup.select('a[href^="/awesome/"]')
        }
    )
    if not categories:
        raise RuntimeError("Scaladex categories unavailable; refusing an empty seed selection")
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
            if not refs:
                break
            seen.update(refs)
            missing = [r for r in refs if r not in inventory]
            for ref, result in parallel(lambda r: (r, project_inventory(fetch, r)), missing):
                inventory[ref] = result
            language_refs = [r for r in refs if r not in languages]
            for ref, data in parallel(
                lambda r: (r, obj(fetch.json(f"https://api.github.com/repos/{r}/languages"))),
                language_refs,
            ):
                languages[ref] = data
            for rank, ref in enumerate(refs, (page - 1) * 20 + 1):
                artifacts, latest = inventory[ref]
                scala = [a for a in artifacts if SCALA_SUFFIX.search(a)]
                language = languages[ref]
                numeric_languages = {
                    k: v for k, v in language.items() if isinstance(v, (int, float))
                }
                primary = (
                    max(numeric_languages, key=lambda k: numeric_languages[k])
                    if numeric_languages
                    else "unknown"
                )
                if not scala or not latest or primary != "Scala":
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
                        "artifacts": artifacts,
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
    destination.write_text(
        yaml.safe_dump(
            {
                "schema": 1,
                "selected_at": datetime.now(timezone.utc).isoformat(),
                "source": INDEX + "/awesome",
                "rule": "Up to 10 Scala artifact-publishing projects per category in default Scaladex order; repository deduplicated",
                "projects": list(projects.values()),
                "exclusions": exclusions,
            },
            sort_keys=False,
        )
    )
    (destination.parent / "selection-evidence.json").write_text(
        json.dumps({"requests": sorted(fetch.used), "failures": fetch.failures}, indent=2)
    )
