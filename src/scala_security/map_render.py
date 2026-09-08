"""Independent, read-only snapshot export and standalone storytelling map."""

from __future__ import annotations

import hashlib
import html as html_text
import json
import math
import sqlite3
import time
from pathlib import Path
from typing import Any

from .map_world import generate_world


def read_snapshot(database: Path) -> dict[str, Any]:
    db = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        projects = []
        for row in db.execute("""SELECT p.id,p.stars,p.categories,s.value,s.maintenance,s.security,
          r.exposure,r.unvalued FROM projects p JOIN scores s ON s.project=p.id
          JOIN ranking r ON r.project=p.id WHERE p.seed=1 ORDER BY p.id"""):
            project = dict(row)
            project["categories"] = json.loads(project["categories"])
            projects.append(project)
        if not projects:
            raise ValueError(
                "Snapshot has no scored seed projects. Analyze it before rendering a map."
            )
        if len(projects) != db.execute("SELECT count(*) FROM projects WHERE seed=1").fetchone()[0]:
            raise ValueError(
                "Some seed projects have no scores or ranking. Analyze the complete snapshot first."
            )
        index = {p["id"]: i for i, p in enumerate(projects)}
        fallout = [[] for _ in projects]
        for row in db.execute("""SELECT f.target,f.dependant,count(s.edge) AS hops FROM fallout f
          JOIN path_steps s ON s.target=f.target AND s.dependant=f.dependant
          GROUP BY f.target,f.dependant ORDER BY f.target,f.dependant"""):
            if row["target"] not in index or row["dependant"] not in index:
                raise ValueError("Map pilot requires a closed seed exposure universe")
            if not 1 <= row["hops"] <= 5:
                raise ValueError("Map pilot requires verified paths of one to five hops")
            fallout[index[row["target"]]].append([index[row["dependant"]], row["hops"]])
        # Refuse silently incomplete exposure exports.
        if sum(map(len, fallout)) != db.execute("SELECT count(*) FROM fallout").fetchone()[0]:
            raise ValueError("A fallout relationship has no retained path")
        metadata = dict(db.execute("SELECT key,value FROM metadata"))
        if metadata.get("universe") != "seed":
            raise ValueError("Map pilot requires a closed seed snapshot")
        for i, project in enumerate(projects):
            expected = sum(projects[j]["value"] or 0 for j, _ in fallout[i])
            if not math.isclose(expected, project["exposure"], abs_tol=1e-8):
                raise ValueError(f"Exposure mismatch: {project['id']}")
        return {
            "projects": projects,
            "fallout": fallout,
            "snapshot": metadata.get("snapshot_id", "unknown"),
            "collected": metadata.get("collected_at", "unknown"),
            "matrix": metadata.get("target_matrix", "{}"),
            "max_hops": max((h for group in fallout for _, h in group), default=5),
            "gaps": db.execute("SELECT count(*) FROM gaps").fetchone()[0],
        }
    finally:
        db.close()


def bind_world(world: dict[str, Any], projects: list[dict[str, Any]]) -> dict[str, Any]:
    """Rank-match visual countries to star prominence, allowing organic sizes."""
    ordered = sorted(projects, key=lambda p: (-(math.sqrt(max(p["stars"] or 0, 0))), p["id"]))
    countries = sorted(world["countries"], key=lambda c: (-c["area"], c["id"]))
    if len(countries) != len(projects):
        raise ValueError("World country count does not match the snapshot")
    for country, project in zip(countries, ordered):
        country["project"] = project["id"]
    world["schema"] = 1
    world["area_policy"] = (
        "Organic country sizes rank-matched to stars; areas are illustrative, not proportional."
    )
    return world


def validate_world(world: dict[str, Any], projects: list[dict[str, Any]]) -> None:
    ids = [c["project"] for c in world.get("countries", [])]
    if world.get("schema") != 1 or len(set(ids)) != len(ids):
        raise ValueError("Invalid world format or duplicate project territories")
    if set(ids) != {p["id"] for p in projects}:
        raise ValueError(
            "Project roster changed. Use --regenerate-world to create a new geography; the existing world is preserved until generation succeeds."
        )
    for country in world["countries"]:
        if not country["path"] or not all(math.isfinite(country[k]) for k in ("x", "y", "area")):
            raise ValueError("Invalid country geometry")


def render_map(
    database: Path,
    output: Path,
    world_path: Path,
    *,
    regenerate: bool = False,
    seed: int = 20260908,
    cache: Path = Path(".cache/azgaar"),
) -> dict[str, Any]:
    start = time.monotonic()
    model = read_snapshot(database)
    fresh = regenerate or not world_path.exists()
    if fresh:
        print(f"Generating {len(model['projects'])} countries with Azgaar...", flush=True)
        world = bind_world(generate_world(len(model["projects"]), seed, cache), model["projects"])
    else:
        world = json.loads(world_path.read_text())
    validate_world(world, model["projects"])
    model["world"] = world
    source = Path(__file__).parent
    html = (source / "templates/map.html").read_text()
    html = html.replace("__CSS__", (source / "templates/map.css").read_text())
    html = html.replace("__JS__", (source / "templates/map.js").read_text())
    html = html.replace(
        "__LICENSE__", html_text.escape((source / "templates/azgaar-license.txt").read_text())
    )
    encoded = json.dumps(model, separators=(",", ":"), ensure_ascii=False).replace("<", "\\u003c")
    html = html.replace("__DATA__", encoded)
    size = len(html.encode())
    if size > 16 * 1024 * 1024:
        raise ValueError("Map exceeds 16 MiB pilot budget; reduce geometry/decorative detail")
    output.parent.mkdir(parents=True, exist_ok=True)
    if fresh:
        world_path.parent.mkdir(parents=True, exist_ok=True)
        temp_world = world_path.with_suffix(".tmp")
        temp_world.write_text(json.dumps(world, separators=(",", ":")))
        temp_world.replace(world_path)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(html)
    temporary.replace(output)
    metrics = {
        "snapshot": model["snapshot"],
        "projects": len(model["projects"]),
        "relationships": sum(map(len, model["fallout"])),
        "html_bytes": size,
        "seconds": round(time.monotonic() - start, 3),
        "generated_world": fresh,
        "world_sha256": hashlib.sha256(world_path.read_bytes()).hexdigest(),
    }
    output.with_suffix(".measurements.json").write_text(json.dumps(metrics, indent=2))
    print(f"Map: {output.resolve()}\n" + json.dumps(metrics, indent=2), flush=True)
    return metrics
