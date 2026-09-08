"""Map snapshot integrity and offline simulation regressions."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright
from test_pipeline import fixture_db

from scala_security.analyze import analyze
from scala_security.map_render import bind_world, read_snapshot, render_map


def map_fixture(tmp_path: Path) -> tuple[Path, Path]:
    database = tmp_path / "snapshot.sqlite"
    db = fixture_db(database)
    db.execute("UPDATE projects SET seed=1")
    db.execute("UPDATE projects SET stars=NULL WHERE id='scala/c'")
    db.execute("INSERT INTO metadata VALUES('universe','seed')")
    analyze(db)
    db.close()
    model = read_snapshot(database)
    world = {
        "width": 2400,
        "height": 1550,
        "seed": 1,
        "land": [],
        "lakes": [],
        "rivers": [],
        "decor": [],
        "countries": [
            {
                "id": i,
                "area": (4 - i) * 10000,
                "x": 500 + i * 500,
                "y": 750,
                "path": f"M{350 + i * 500} 600h300v300h-300Z",
            }
            for i in range(3)
        ],
    }
    path = tmp_path / "world.json"
    path.write_text(json.dumps(bind_world(world, model["projects"])))
    return database, path


def test_refresh_is_read_only_and_preserves_world(tmp_path: Path) -> None:
    database, world = map_fixture(tmp_path)
    before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (database, world)]
    output = tmp_path / "map.html"
    render_map(database, output, world)
    assert before == [hashlib.sha256(p.read_bytes()).hexdigest() for p in (database, world)]
    model = read_snapshot(database)
    index = {p["id"]: i for i, p in enumerate(model["projects"])}
    # A uses B v1, but only B v2 depends on C. No false A -> C exposure.
    assert model["fallout"][index["scala/c"]] == [[index["scala/b"], 1]]
    assert model["projects"][index["scala/c"]]["value"] is None
    assert "__DATA__" not in output.read_text()
    first = output.read_bytes()
    render_map(database, output, world)
    assert output.read_bytes() == first


def test_roster_change_fails_without_overwriting_artifacts(tmp_path: Path) -> None:
    database, world = map_fixture(tmp_path)
    output = tmp_path / "map.html"
    output.write_text("previous reviewed map")
    saved = json.loads(world.read_text())
    saved["countries"][0]["project"] = "removed/project"
    world.write_text(json.dumps(saved))
    before = world.read_bytes()
    with pytest.raises(ValueError, match="roster changed"):
        render_map(database, output, world)
    assert output.read_text() == "previous reviewed map"
    assert world.read_bytes() == before


def test_map_simulation_offline_unknowns_and_keyboard_search(tmp_path: Path) -> None:
    database, world = map_fixture(tmp_path)
    output = tmp_path / "map.html"
    render_map(database, output, world)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(offline=True, viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        errors = []
        requests = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: requests.append(request.url))
        page.goto(output.as_uri())
        assert page.locator("html").get_attribute("data-map-ready") == "true"
        assert page.locator(".country").count() == 3
        assert page.locator("#layer").input_value() == "exposure"
        for name in ("scala/c", "scala/b"):
            page.get_by_label("Find a project").fill(name)
            page.get_by_label("Find a project").press("Enter")
            page.get_by_role("button", name="Compromise this project", exact=True).click()
            if name == "scala/c":
                assert page.locator("#compromised-count").inner_text() == "1"
                assert page.locator("#exposed-count").inner_text() == "1"
                assert page.locator("#affected-percent").inner_text() == "66.7"
        # B is both directly compromised and a dependant of C; count it once.
        assert page.locator("#compromised-count").inner_text() == "2"
        assert page.locator("#exposed-count").inner_text() == "1"
        assert page.locator("#affected-percent").inner_text() == "100.0"
        assert page.locator("#value-percent").inner_text() == "100.0%"
        assert "1 affected / 1 total" in page.locator("#impact-note").inner_text()
        for layer in ("security", "maintenance", "value", "exposure"):
            page.get_by_label("Map layer", exact=True).select_option(layer)
            assert page.locator("#affected-percent").inner_text() == "100.0"
        page.get_by_label("Map layer", exact=True).select_option("security")
        assert page.locator('.country[style*="unknown"]').count() == 3
        page.get_by_role("button", name="Reset", exact=True).click()
        assert page.locator("#affected-percent").inner_text() == "0.0"
        page.get_by_role("button", name="Fit whole map").click()
        assert page.locator("#world").get_attribute("transform") == "translate(0 0) scale(1)"
        page.get_by_role("button", name="Zoom in", exact=True).click()
        assert "scale(1.5)" in (page.locator("#world").get_attribute("transform") or "")
        page.get_by_role("button", name="About this world").click()
        assert page.locator("#about").is_visible()
        page.keyboard.press("Escape")
        assert not page.locator("#about").is_visible()
        for width in (390, 900, 1440):
            page.set_viewport_size({"width": width, "height": 900})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert not errors
        assert all(url.startswith("file:") for url in requests)
        browser.close()
