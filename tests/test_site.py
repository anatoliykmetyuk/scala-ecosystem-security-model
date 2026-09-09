"""The website command reuses analysis and produces a navigable offline site."""

import hashlib
from pathlib import Path

from playwright.sync_api import sync_playwright
from test_map import map_fixture

from scala_security.cli import main


def test_website_command_preserves_analysis_and_navigation(tmp_path: Path, monkeypatch):
    database, world = map_fixture(tmp_path)
    before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (database, world)]
    output = tmp_path / "website"
    monkeypatch.setattr(
        "sys.argv",
        [
            "scala-security",
            "render-site",
            "--database",
            str(database),
            "--world",
            str(world),
            "--output",
            str(output),
        ],
    )
    main()
    assert before == [hashlib.sha256(p.read_bytes()).hexdigest() for p in (database, world)]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(offline=True)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto((output / "index.html").as_uri())
        assert page.get_by_role("heading", name="Scala Land").is_visible()
        page.get_by_role("link", name="Rankings").click()
        assert page.locator(".rank-button").count() == 3
        page.get_by_role("link", name="Scala Land home").click()
        page.get_by_role("link", name="Atlas").click()
        page.wait_for_function("document.documentElement.dataset.mapReady === 'true'")
        page.get_by_role("link", name="Scala Land home").click()
        assert page.get_by_role("heading", name="Scala Land").is_visible()
        assert not errors
        browser.close()
