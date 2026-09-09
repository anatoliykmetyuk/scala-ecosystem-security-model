"""Generate the complete local website from a read-only analyzed snapshot."""

import base64
import sqlite3
from pathlib import Path

from .map_render import render_map
from .render import render


def render_site(
    database: Path,
    output: Path,
    world: Path,
    *,
    regenerate: bool = False,
    seed: int = 20260908,
    cache: Path = Path(".cache/azgaar"),
) -> None:
    # Report rendering records template metadata. Keep those writes in memory,
    # leaving the shared analysis and its provenance untouched.
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as source:
        with sqlite3.connect(":memory:") as snapshot:
            source.backup(snapshot)
            snapshot.row_factory = sqlite3.Row
            render(snapshot, output / "preview.html")
    render_map(
        database,
        output / "ecosystem-map.html",
        world,
        regenerate=regenerate,
        seed=seed,
        cache=cache,
    )
    templates = Path(__file__).parent / "templates"
    logo = (templates / "scala-logo.svg").read_text()
    logo = logo[logo.index("<svg") :]
    landing = (templates / "index.html").read_text().replace("__SCALA_LOGO__", logo)
    background = base64.b64encode((templates / "alpine-background.png").read_bytes()).decode(
        "ascii"
    )
    landing = landing.replace("__ALPINE_BACKGROUND__", f"data:image/png;base64,{background}")
    (output / "index.html").write_text(landing)
    print(f"Website: {(output / 'index.html').resolve()}", flush=True)
