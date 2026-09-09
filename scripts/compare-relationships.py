"""Explain removed witness paths without modifying either snapshot."""

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path

from scala_security.data import owned_versions


def compare(old_path: Path, new_path: Path) -> dict:
    old = sqlite3.connect(old_path.resolve().as_uri() + "?mode=ro", uri=True)
    new = sqlite3.connect(new_path.resolve().as_uri() + "?mode=ro", uri=True)
    old.row_factory = new.row_factory = sqlite3.Row
    before = set(map(tuple, old.execute("SELECT * FROM fallout")))
    after = set(map(tuple, new.execute("SELECT * FROM fallout")))
    removed = []
    for target, dependant in sorted(before - after):
        causes = []
        witness = list(
            old.execute(
                "SELECT e.* FROM path_steps p JOIN edges e ON e.id=p.edge WHERE p.target=? AND p.dependant=? ORDER BY p.position",
                (target, dependant),
            )
        )
        for edge in witness:
            for key in (edge["source"], edge["target"]):
                artifact, version = key.rsplit("@", 1)
                if not new.execute(
                    "SELECT 1 FROM target_artifacts WHERE artifact=?", (artifact,)
                ).fetchone():
                    selection = [
                        dict(r)
                        for r in new.execute(
                            "SELECT * FROM artifact_selection WHERE artifact=?", (artifact,)
                        )
                    ]
                    causes.append(
                        {
                            "reason": "selection cap"
                            if selection
                            else "matrix/discovery eligibility",
                            "version": key,
                            "selection": selection,
                        }
                    )
                    continue
                previous = old.execute(
                    f"SELECT project FROM {owned_versions(old)} WHERE id=?", (key,)
                ).fetchone()
                current = new.execute(
                    f"SELECT project FROM {owned_versions(new)} WHERE id=?", (key,)
                ).fetchone()
                if current and previous and current[0] != previous[0]:
                    causes.append(
                        {
                            "reason": "publication ownership",
                            "version": key,
                            "before": previous[0],
                            "after": current[0],
                        }
                    )
            match = new.execute(
                "SELECT 1 FROM edges WHERE source=? AND target=? AND scope=? AND optional IS ? AND exact=?",
                (edge["source"], edge["target"], edge["scope"], edge["optional"], edge["exact"]),
            ).fetchone()
            if not match:
                alternatives = [
                    dict(r)
                    for r in new.execute(
                        "SELECT * FROM edges WHERE source=? AND target=?",
                        (edge["source"], edge["target"]),
                    )
                ]
                gaps = [
                    dict(r)
                    for r in new.execute("SELECT * FROM gaps WHERE subject=?", (edge["source"],))
                ]
                causes.append(
                    {
                        "reason": "changed or unavailable declaration",
                        "source": edge["source"],
                        "target": edge["target"],
                        "new_edges": alternatives,
                        "gaps": gaps,
                    }
                )
        latest = new.execute("SELECT latest FROM projects WHERE id=?", (dependant,)).fetchone()
        if witness and latest and witness[0]["source"].rsplit("@", 1)[1] != latest[0]:
            causes.append({"reason": "consumer release changed", "latest": latest[0]})
        removed.append({"target": target, "dependant": dependant, "causes": causes})
    counts = Counter(reason for row in removed for reason in {c["reason"] for c in row["causes"]})
    return {
        "before": len(before),
        "after": len(after),
        "retained": len(before & after),
        "added": len(after - before),
        "removed": len(before - after),
        "overlapping_cause_counts": dict(counts),
        "unexplained": sum(not r["causes"] for r in removed),
        "removed_relationships": removed,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("old", type=Path)
    parser.add_argument("new", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.old, args.new)
    args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != "removed_relationships"}, indent=2))
