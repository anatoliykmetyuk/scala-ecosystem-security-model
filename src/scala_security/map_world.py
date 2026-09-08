"""Pinned build-time Azgaar adapter; its editor is not included in map HTML."""

from __future__ import annotations

import functools
import hashlib
import io
import json
import shutil
import subprocess
import tarfile
import threading
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

AZGAAR_REVISION = "f30ffd812e391f9f979d5a3c54be99e2b4920b64"
AZGAAR_ARCHIVE_SHA256 = "00f2fc8550c3b0c4b1ea8a4dccea4102756bbec449e1796e529b7e994f15ae25"


def install_generator(cache: Path) -> Path:
    root = cache / f"Fantasy-Map-Generator-{AZGAAR_REVISION}"
    marker = root / "scalaland-build.json"
    if marker.exists() and (root / "dist/index.html").exists():
        return root / "dist"
    if not shutil.which("npm"):
        raise RuntimeError(
            "World generation requires Node.js 24+ and npm. Refreshing a saved world does not."
        )
    if not root.exists():
        url = f"https://codeload.github.com/Azgaar/Fantasy-Map-Generator/tar.gz/{AZGAAR_REVISION}"
        print("Downloading pinned Azgaar generator (first world build only)...", flush=True)
        with urllib.request.urlopen(url, timeout=90) as response:
            archive = response.read()
        if hashlib.sha256(archive).hexdigest() != AZGAAR_ARCHIVE_SHA256:
            raise RuntimeError("Azgaar archive checksum mismatch")
        cache.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
            bundle.extractall(cache, filter="data")
    for command in (
        ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"],
        ["npm", "exec", "--", "vite", "build", "--base=/"],
    ):
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=240)
        if result.returncode:
            raise RuntimeError(f"Azgaar build failed: {result.stderr[-3000:]}")
    marker.write_text(json.dumps({"revision": AZGAAR_REVISION}))
    return root / "dist"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


def generate_world(count: int, seed: int, cache: Path) -> dict[str, Any]:
    """Use a disposable headless browser as Azgaar's build runtime, localhost only."""
    from playwright.sync_api import sync_playwright

    directory = install_generator(cache)
    handler = functools.partial(QuietHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context(viewport={"width": 1200, "height": 800})
            port = server.server_port
            origin = f"http://127.0.0.1:{port}"
            context.route(
                "**/*",
                lambda route: (
                    route.continue_()
                    if route.request.url.startswith(origin + "/")
                    else route.abort()
                ),
            )
            page = context.new_page()
            page.goto(origin + "/?seed=548", wait_until="load", timeout=60000)
            page.wait_for_function(
                "typeof pack !== 'undefined' && pack.states?.length > 1 && typeof getIsolines === 'function'",
                timeout=60000,
            )
            # Generation and export are an application build step, not viewer work.
            adapter = Path(__file__).with_name("map_generate.js").read_text()
            world = page.evaluate(adapter, {"count": count, "seed": seed})
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    world["generator"] = {"name": "Azgaar", "revision": AZGAAR_REVISION}
    return world
