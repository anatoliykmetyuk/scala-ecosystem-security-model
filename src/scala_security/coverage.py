"""Outgoing release evidence coverage, independent of incoming fallout counts."""

import json
import sqlite3
from typing import Any

from .data import owned_versions


def project_coverage(db: sqlite3.Connection, project: str) -> dict[str, Any]:
    latest = db.execute("SELECT latest FROM projects WHERE id=?", (project,)).fetchone()[0]
    artifacts = [
        r[0]
        for r in db.execute(
            "SELECT a.id FROM target_artifacts t JOIN artifacts a ON a.id=t.artifact WHERE a.project=?",
            (project,),
        )
    ]
    roots = list(
        db.execute(
            f"SELECT v.id,v.fetched FROM {owned_versions(db)} v WHERE v.project=? AND v.number=?",
            (project, latest),
        )
    )
    selected = {r[0] for r in db.execute("SELECT artifact FROM target_artifacts")}
    roots = [r for r in roots if r[0].rsplit("@", 1)[0] in selected]
    artifacts = sorted(set(artifacts) | {r[0].rsplit("@", 1)[0] for r in roots})
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    coverage = (
        dict(
            (r[0], r)
            for r in db.execute(
                f"SELECT c.* FROM version_coverage c JOIN {owned_versions(db)} v ON v.id=c.version WHERE v.project=? AND v.number=?",
                (project, latest),
            )
        )
        if "version_coverage" in tables
        else {}
    )
    publications = (
        list(
            db.execute(
                "SELECT verified,issues FROM publications WHERE project=? AND version=?",
                (project, latest),
            )
        )
        if "publications" in tables
        else []
    )
    usable = complete = fetched = 0
    reasons: set[str] = set()
    for key, available in roots:
        fetched += bool(available)
        if key in coverage:
            record = coverage[key]
            usable += bool(record[1])
            complete += bool(record[2])
            reasons.update(json.loads(record[3]))
        elif available:
            # Historical snapshots lack declaration-level coverage. Retain their
            # verified paths but never label a fetch as complete resolution.
            has_edges = db.execute(
                "SELECT 1 FROM edges WHERE source=? AND exact=1 AND scope!='unknown' LIMIT 1",
                (key,),
            ).fetchone()
            usable += bool(has_edges)
            reasons.add("Historical snapshot lacks declaration-resolution coverage")
        else:
            reasons.add("Release artifact fetch failed")
    gaps = db.execute(
        f"SELECT stage,subject,reason FROM gaps WHERE subject=? OR subject IN (SELECT id FROM {owned_versions(db)} WHERE project=? AND number=?)",
        (project, project, latest),
    ).fetchall()
    reasons.update(
        r[2] for r in gaps if r[0] in {"release", "version", "declaration", "dependency_evidence"}
    )
    if not latest:
        reasons.add("Project latest release unavailable")
    elif not roots:
        reasons.add("No selected matching release coordinates")
    elif not usable:
        reasons.add("No release artifacts have usable dependency evidence")
    status = (
        "unavailable"
        if not usable
        else "complete"
        if complete == len(roots) and len(roots) == len(artifacts)
        else "partial"
    )
    if not usable:
        for publication in publications:
            reasons.update(json.loads(publication[1]))
    return {
        "checked": len(publications),
        "verified": sum(r[0] for r in publications),
        "status": status,
        "release": latest,
        "selected": len(artifacts),
        "roots": len(roots),
        "fetched": fetched,
        "usable": usable,
        "complete": complete,
        "reasons": sorted(reasons),
    }
