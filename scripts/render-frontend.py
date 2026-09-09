"""Generate the local website using this worktree's source and shared analysis."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    from scala_security.site_render import render_site

    output = ROOT / "output"
    database = Path((output / "latest-database.txt").read_text().strip())
    render_site(database, output, output / "map/world.json", cache=ROOT / ".cache/azgaar")


if __name__ == "__main__":
    main()
