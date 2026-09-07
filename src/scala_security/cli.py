"""Command-line entry points for reproducible collection and rendering."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import yaml

from .analyze import analyze, validate
from .collect import Collector
from .data import connect, obj, rows
from .http import Fetcher
from .seeds import select


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["select", "rebuild", "render", "validate"])
    parser.add_argument("--seeds", type=Path, default=Path("config/seeds.yaml"))
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument(
        "--reuse-cache",
        type=Path,
        help="Explicitly reuse a prior evidence directory; default collects fresh",
    )
    parser.add_argument("--database", type=Path, help="Database to render or validate")
    args = parser.parse_args()
    if args.command == "select":
        select(
            Fetcher(
                args.reuse_cache
                or args.output
                / "selection-evidence"
                / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            ),
            args.seeds,
        )
        return
    if args.command == "rebuild":
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        run = args.output / "runs" / stamp
        run.mkdir(parents=True)
        db = connect(run / "snapshot.sqlite")
        seed_bytes = args.seeds.read_bytes()
        (run / "seeds.yaml").write_bytes(seed_bytes)
        db.execute(
            "INSERT INTO metadata VALUES(?,?)",
            ("seed_sha256", hashlib.sha256(seed_bytes).hexdigest()),
        )
        db.execute("INSERT INTO metadata VALUES(?,?)", ("snapshot_id", stamp))
        db.execute(
            "INSERT INTO metadata VALUES(?,?)",
            ("model_version", version("scala-ecosystem-security-model")),
        )
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
        db.execute("INSERT INTO metadata VALUES(?,?)", ("code_revision", revision or "unavailable"))
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True
        ).stdout.strip()
        db.execute("INSERT INTO metadata VALUES(?,?)", ("code_dirty", str(bool(dirty)).lower()))
        source = Path(__file__).parent
        source_hash = hashlib.sha256()
        for file in sorted(source.rglob("*")):
            if file.suffix in (".py", ".html"):
                source_hash.update(str(file.relative_to(source)).encode())
                source_hash.update(file.read_bytes())
        db.execute("INSERT INTO metadata VALUES(?,?)", ("source_sha256", source_hash.hexdigest()))
        fetch = Fetcher(args.reuse_cache or run / "evidence")
        Collector(db, fetch).run(rows(obj(yaml.safe_load(seed_bytes)).get("projects")))
        analyze(db)
    else:
        path = args.database
        if path is None:
            path = Path((args.output / "latest-database.txt").read_text().strip())
        if not path.exists():
            parser.error(f"Database does not exist: {path}")
        db = connect(path)
        run = path.parent
    metrics = validate(db)
    (run / "validation.json").write_text(json.dumps(metrics, indent=2))
    if args.command != "validate":
        from .render import render

        render(db, args.output / "preview.html")
        (args.output / "latest-database.txt").write_text(
            str(Path(db.execute("PRAGMA database_list").fetchone()[2]).resolve())
        )
    print(json.dumps(metrics, indent=2))
    db.close()


if __name__ == "__main__":
    main()
