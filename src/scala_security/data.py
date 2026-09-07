"""Typed boundaries for untrusted JSON and normalized persistent records."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.parse import urlparse

JSON = None | bool | int | float | str | list["JSON"] | dict[str, "JSON"]


def obj(value: object) -> dict[str, JSON]:
    if not isinstance(value, dict):
        return {}
    return value


def rows(value: object) -> list[dict[str, JSON]]:
    return [obj(x) for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def string(value: object) -> str:
    return value if isinstance(value, str) else ""


def number(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def repo_name(value: object) -> str:
    url = string(value)
    parts = urlparse(url.removeprefix("scm:git:").removeprefix("git+"))
    if parts.hostname not in ("github.com", "www.github.com"):
        return ""
    bits = parts.path.strip("/").removesuffix(".git").split("/")
    return "/".join(bits[:2]).lower() if len(bits) >= 2 else ""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, stars INTEGER, seed INTEGER NOT NULL DEFAULT 0,
      categories TEXT NOT NULL DEFAULT '[]', latest TEXT, source TEXT, stars_observed TEXT);
    CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY, project TEXT REFERENCES projects(id),
      latest TEXT, published TEXT, source TEXT);
    CREATE INDEX IF NOT EXISTS artifacts_project ON artifacts(project);
    CREATE TABLE IF NOT EXISTS target_artifacts(artifact TEXT PRIMARY KEY REFERENCES artifacts(id));
    CREATE TABLE IF NOT EXISTS coordinate_checks(project TEXT REFERENCES projects(id), artifact TEXT, published INTEGER NOT NULL, PRIMARY KEY(project,artifact));
    CREATE TABLE IF NOT EXISTS versions(id TEXT PRIMARY KEY, artifact TEXT NOT NULL REFERENCES artifacts(id),
      number TEXT NOT NULL, fetched INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS edges(id INTEGER PRIMARY KEY, source TEXT REFERENCES versions(id),
      target TEXT REFERENCES versions(id), scope TEXT NOT NULL, optional INTEGER, exact INTEGER NOT NULL,
      evidence TEXT, UNIQUE(source,target,scope,optional));
    CREATE INDEX IF NOT EXISTS edges_source ON edges(source);
    CREATE INDEX IF NOT EXISTS edges_target ON edges(target);
    CREATE TABLE IF NOT EXISTS observations(project TEXT REFERENCES projects(id), kind TEXT, payload TEXT,
      source TEXT, PRIMARY KEY(project,kind));
    CREATE TABLE IF NOT EXISTS gaps(stage TEXT, subject TEXT, reason TEXT,
      UNIQUE(stage,subject,reason));
    CREATE TABLE IF NOT EXISTS scores(project TEXT PRIMARY KEY REFERENCES projects(id), value REAL,
      maintenance REAL, security REAL, explanation TEXT);
    CREATE TABLE IF NOT EXISTS fallout(target TEXT REFERENCES projects(id), dependant TEXT REFERENCES projects(id),
      PRIMARY KEY(target,dependant));
    CREATE TABLE IF NOT EXISTS path_steps(target TEXT, dependant TEXT, position INTEGER,
      edge INTEGER REFERENCES edges(id), PRIMARY KEY(target,dependant,position),
      FOREIGN KEY(target,dependant) REFERENCES fallout(target,dependant));
    CREATE TABLE IF NOT EXISTS ranking(project TEXT PRIMARY KEY REFERENCES projects(id),
      exposure REAL NOT NULL, dependants INTEGER NOT NULL, unvalued INTEGER NOT NULL, candidate INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS requests(url TEXT PRIMARY KEY, cache_path TEXT, status INTEGER, retrieved_at TEXT);
    """)
    db.execute("INSERT OR IGNORE INTO metadata VALUES('schema_version','1')")
    return db
