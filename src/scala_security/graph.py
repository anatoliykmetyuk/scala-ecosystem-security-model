"""Version-specific paths; only terminal target matching ignores target version."""

from __future__ import annotations

import sqlite3
from collections import deque
from dataclasses import dataclass

from .configuration import MAX_HOPS
from .data import owned_versions


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
    return edge.scope in scopes and (depth == 0 or edge.optional is False) and edge.exact


def paths(
    db: sqlite3.Connection,
    roots: list[str],
    max_hops: int = MAX_HOPS,
    targets: set[str] | None = None,
    within: set[str] | None = None,
) -> dict[str, list[int]]:
    roots = [root for root in roots if within is None or root.rsplit("@", 1)[0] in within]
    seeds = {r[0] for r in db.execute("SELECT id FROM projects WHERE seed=1")}
    queue = deque((root, []) for root in roots)
    visited = set(roots)
    found: dict[str, list[int]] = {}
    version_table = owned_versions(db)
    while queue:
        source, path = queue.popleft()
        if len(path) == max_hops:
            continue
        for row in db.execute(
            f"""SELECT e.*, v.project, v.artifact FROM edges e JOIN {version_table} v ON v.id=e.target
                WHERE e.source=? ORDER BY e.target,e.scope,e.id""",
            (source,),
        ):
            if within is not None and (
                row["artifact"] not in within or row["project"] not in seeds
            ):
                continue
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
            if (
                edge.project
                and edge.project not in found
                and (targets is None or row["artifact"] in targets)
            ):
                found[edge.project] = extended
            if edge.target not in visited:
                visited.add(edge.target)
                queue.append((edge.target, extended))
    return found
