"""Version-specific paths; only terminal target matching ignores target version."""

from __future__ import annotations

import sqlite3
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class Edge:
    id: int
    source: str
    target: str
    project: str | None
    scope: str
    optional: bool | None
    exact: bool


def allowed(edge: Edge, depth: int) -> bool:
    scopes = {"compile", "runtime"}
    if depth == 0:
        scopes |= {"test", "build", "development", "provided"}
    return edge.scope in scopes and edge.optional is False and edge.exact


def paths(db: sqlite3.Connection, roots: list[str], max_hops: int = 3) -> dict[str, list[int]]:
    queue = deque((root, []) for root in roots)
    visited = set(roots)
    found: dict[str, list[int]] = {}
    while queue:
        source, path = queue.popleft()
        if len(path) == max_hops:
            continue
        for row in db.execute(
            """SELECT e.*, a.project FROM edges e JOIN versions v ON v.id=e.target
                                 JOIN artifacts a ON a.id=v.artifact WHERE e.source=? ORDER BY e.id""",
            (source,),
        ):
            edge = Edge(
                row["id"],
                source,
                row["target"],
                row["project"],
                row["scope"],
                None if row["optional"] is None else bool(row["optional"]),
                bool(row["exact"]),
            )
            if not allowed(edge, len(path)):
                continue
            extended = path + [edge.id]
            if edge.project and edge.project not in found:
                found[edge.project] = extended
            if edge.target not in visited:
                visited.add(edge.target)
                queue.append((edge.target, extended))
    return found
