"""Command-line entry points for reproducible collection and rendering."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import yaml

from .analyze import analyze, validate
from .collect import Collector
from .configuration import parse_config
from .data import connect
from .http import Fetcher
from .seeds import select


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["select", "rebuild", "render", "validate", "plan"])
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
    if args.command in {"rebuild", "plan"}:
        seed_bytes = args.seeds.read_bytes()
        config = parse_config(yaml.safe_load(seed_bytes))
        if args.command == "plan":
            print(
                json.dumps(
                    {
                        "projects": len(config.projects),
                        "modules": config.module_count,
                        "universe": "seed",
                        "max_artifacts_per_project": 10,
                        "matrix": config.matrix,
                        "selected_coordinate_upper_bound": sum(
                            min(10, len(config.coordinates(p))) for p in config.projects
                        ),
                        "candidate_coordinates": len(
                            {a for p in config.projects for a in config.coordinates(p)}
                        ),
                        "note": "Uncapped offline candidates; final top 10 selection requires publication checks and dependent-package counts during collection.",
                    },
                    indent=2,
                )
            )
            return
    if args.command == "rebuild":
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        run = args.output / "runs" / stamp
        run.mkdir(parents=True)
        db = connect(run / "snapshot.sqlite")
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
        Collector(db, fetch, config).run(config.projects)
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

        render_start = time.monotonic()
        render(db, args.output / "preview.html")
        db.execute(
            "INSERT OR REPLACE INTO metadata VALUES(?,?)",
            ("render_seconds", str(time.monotonic() - render_start)),
        )
        db.commit()
        (args.output / "latest-database.txt").write_text(
            str(Path(db.execute("PRAGMA database_list").fetchone()[2]).resolve())
        )
    measurements = {
        "seconds": {
            row[0]: float(row[1])
            for row in db.execute("SELECT key,value FROM metadata WHERE key LIKE '%_seconds'")
        },
        "database_bytes": Path(db.execute("PRAGMA database_list").fetchone()[2]).stat().st_size,
        "evidence_bytes": sum(
            path.stat().st_size
            for row in db.execute("SELECT cache_path FROM requests")
            if (path := Path(row[0])).exists()
        ),
    }
    if args.command != "validate":
        measurements["preview_bytes"] = (args.output / "preview.html").stat().st_size
    (run / "measurements.json").write_text(json.dumps(measurements, indent=2))
    print(json.dumps({"counts": metrics, "measurements": measurements}, indent=2))
    db.close()


if __name__ == "__main__":
    main()
