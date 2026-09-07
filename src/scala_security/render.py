"""Standalone report with a compact, normalized embedded view model."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .data import JSON

MAX_PREVIEW_BYTES = 24 * 1024 * 1024


def render(db: sqlite3.Connection, destination: Path) -> None:
    people = db.execute(
        "SELECT p.id,p.stars,s.value FROM projects p JOIN scores s ON s.project=p.id ORDER BY p.id"
    ).fetchall()
    ids = {p["id"]: i for i, p in enumerate(people)}
    edges = db.execute(
        "SELECT * FROM edges WHERE id IN (SELECT edge FROM path_steps) ORDER BY id"
    ).fetchall()
    edge_ids = {e["id"]: i for i, e in enumerate(edges)}
    targets: list[dict[str, JSON]] = []
    for (
        row
    ) in db.execute("""SELECT r.*,s.maintenance,s.security,s.explanation,p.categories FROM ranking r
      JOIN scores s ON s.project=r.project JOIN projects p ON p.id=r.project
      ORDER BY r.candidate DESC,r.exposure DESC,r.project"""):
        dependants = []
        for d in db.execute(
            """SELECT f.dependant,s.value FROM fallout f JOIN scores s ON s.project=f.dependant
                              WHERE f.target=? ORDER BY s.value DESC,f.dependant""",
            (row["project"],),
        ):
            path = [
                edge_ids[p[0]]
                for p in db.execute(
                    "SELECT edge FROM path_steps WHERE target=? AND dependant=? ORDER BY position",
                    (row["project"], d["dependant"]),
                )
            ]
            dependants.append([ids[d["dependant"]], path])
        sources = {
            s["kind"]: s["source"]
            for s in db.execute(
                "SELECT kind,source FROM observations WHERE project=?", (row["project"],)
            )
        }
        targets.append(
            {
                "project": ids[row["project"]],
                "exposure": row["exposure"],
                "unvalued": row["unvalued"],
                "candidate": bool(row["candidate"]),
                "categories": json.loads(row["categories"]),
                "health": json.loads(row["explanation"]),
                "dependants": dependants,
                "sources": sources,
            }
        )
    metadata = dict(db.execute("SELECT key,value FROM metadata"))
    gaps = db.execute("SELECT count(*) FROM gaps").fetchone()[0]
    model = {
        "projects": [list(p) for p in people],
        "edges": [[e["source"], e["target"], e["scope"], e["evidence"]] for e in edges],
        "targets": targets,
        "metadata": metadata,
        "gaps": gaps,
        "counts": {
            t: db.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            for t in ("artifacts", "versions", "edges", "fallout")
        },
    }
    text = (Path(__file__).parent / "templates" / "report.html").read_text()
    text = text.replace(
        "__DATA__",
        json.dumps(model, separators=(",", ":"), ensure_ascii=False).replace("<", "\\u003c"),
    )
    size = len(text.encode())
    if size > MAX_PREVIEW_BYTES:
        raise RuntimeError(
            f"Preview is {size} bytes, above {MAX_PREVIEW_BYTES} budget; no dependants have been silently dropped"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text)
    print(f"Preview: {destination.resolve()} ({size:,} bytes)", flush=True)
