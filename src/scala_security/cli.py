"""Command-line entry points for reproducible collection and rendering."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
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
