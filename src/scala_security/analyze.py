"""Derive repository-deduplicated fallout from the normalized snapshot."""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime

from .data import obj
from .graph import paths
from .scoring import health, value


def analyze(db: sqlite3.Connection) -> None:
    start = time.monotonic()
    now = datetime.fromisoformat(
        db.execute("SELECT value FROM metadata WHERE key='collected_at'").fetchone()[0]
    )
    db.executescript(
        "DELETE FROM path_steps; DELETE FROM fallout; DELETE FROM ranking; DELETE FROM scores;"
    )
    seeds = {r[0] for r in db.execute("SELECT id FROM projects WHERE seed=1")}
    for project in db.execute("SELECT * FROM projects").fetchall():
        observations = {
            r["kind"]: obj(json.loads(r["payload"]))
            for r in db.execute("SELECT * FROM observations WHERE project=?", (project["id"],))
        }
        result = (
            health(
                observations.get("repository", {}),
                observations.get("commits", {}),
                observations.get("scorecard", {}),
                now,
            )
            if project["seed"]
            else None
        )
        db.execute(
            "INSERT INTO scores VALUES(?,?,?,?,?)",
            (
                project["id"],
                value(project["stars"]),
                result.maintenance if result else None,
                result.security if result else None,
                json.dumps(result.payload()) if result else "{}",
            ),
        )
        if not project["latest"]:
            continue
        roots = [
            r[0]
            for r in db.execute(
                """SELECT v.id FROM versions v JOIN artifacts a ON a.id=v.artifact
          WHERE a.project=? AND v.number=? AND v.fetched=1""",
                (project["id"], project["latest"]),
            )
        ]
        for target, path in paths(db, roots).items():
            if target not in seeds or target == project["id"]:
                continue
            db.execute("INSERT OR IGNORE INTO fallout VALUES(?,?)", (target, project["id"]))
            db.executemany(
                "INSERT INTO path_steps VALUES(?,?,?,?)",
                [(target, project["id"], i, e) for i, e in enumerate(path)],
            )
    db.execute("""INSERT INTO ranking
      SELECT p.id,coalesce(sum(s.value),0),count(f.dependant),count(f.dependant)-count(s.value),
       CASE WHEN count(f.dependant)>0 AND (own.maintenance<0.5 OR own.security<0.5) THEN 1 ELSE 0 END
      FROM projects p JOIN scores own ON own.project=p.id
      LEFT JOIN fallout f ON f.target=p.id LEFT JOIN scores s ON s.project=f.dependant
      WHERE p.seed=1 GROUP BY p.id""")
    db.execute(
        "INSERT OR REPLACE INTO metadata VALUES(?,?)",
        ("analysis_seconds", str(time.monotonic() - start)),
    )
    db.commit()


def validate(db: sqlite3.Connection) -> dict[str, int]:
    assert not db.execute("PRAGMA foreign_key_check").fetchall()
    assert not db.execute(
        "SELECT 1 FROM scores WHERE value<0 OR value>1 OR maintenance<0 OR maintenance>1 OR security<0 OR security>1"
    ).fetchall()
    assert not db.execute("SELECT 1 FROM fallout WHERE target=dependant").fetchall()
    for row in db.execute("SELECT * FROM ranking"):
        expected = db.execute(
            "SELECT coalesce(sum(s.value),0) FROM fallout f JOIN scores s ON s.project=f.dependant WHERE f.target=?",
            (row["project"],),
        ).fetchone()[0]
        assert abs(row["exposure"] - expected) < 1e-9
    for row in db.execute("SELECT * FROM fallout"):
        path = db.execute(
            """SELECT e.*,s.position FROM path_steps s JOIN edges e ON e.id=s.edge
           WHERE s.target=? AND s.dependant=? ORDER BY s.position""",
            (row["target"], row["dependant"]),
        ).fetchall()
        assert 1 <= len(path) <= 3
        for i, edge in enumerate(path):
            assert edge["exact"] and edge["optional"] == 0
            assert edge["scope"] in (
                {"compile", "runtime", "test", "provided", "build", "development"}
                if i == 0
                else {"compile", "runtime"}
            )
            if i:
                assert path[i - 1]["target"] == edge["source"]
        start = db.execute(
            "SELECT a.project,v.number,p.latest FROM versions v JOIN artifacts a ON a.id=v.artifact JOIN projects p ON p.id=a.project WHERE v.id=?",
            (path[0]["source"],),
        ).fetchone()
        end = db.execute(
            "SELECT a.project FROM versions v JOIN artifacts a ON a.id=v.artifact WHERE v.id=?",
            (path[-1]["target"],),
        ).fetchone()
        assert start["project"] == row["dependant"] and start["number"] == start["latest"]
        assert end["project"] == row["target"]
    return {
        table: db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in ("projects", "artifacts", "versions", "edges", "fallout", "gaps")
    }
