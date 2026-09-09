"""Map snapshot integrity and offline simulation regressions."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright
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
        browser = getattr(p, os.environ.get("MAP_TEST_BROWSER", "chromium")).launch()
        context = browser.new_context(offline=True, viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        errors = []
        requests = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: requests.append(request.url))
        page.goto(output.as_uri())
        assert page.locator("html").get_attribute("data-map-ready") == "true"
        assert page.locator(".country").count() == 3
        assert page.locator('[data-layer="exposure"]').get_attribute("aria-pressed") == "true"
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
            button = page.locator(f'[data-layer="{layer}"]')
            button.hover()
            expect(button.get_by_role("tooltip")).to_be_visible()
            button.click()
            expect(button).to_have_attribute("aria-pressed", "true")
            assert page.locator('[data-layer][aria-pressed="true"]').count() == 1
            assert page.locator("#affected-percent").inner_text() == "100.0"
        page.locator('[data-layer="security"]').focus()
        page.keyboard.press("Enter")
        expect(page.locator('[data-layer="security"]')).to_have_attribute("aria-pressed", "true")
        assert page.locator('.country[style*="unknown"]').count() == 3
        page.get_by_role("button", name="Reset", exact=True).click()
        assert page.locator("#affected-percent").inner_text() == "0.0"
        page.get_by_role("button", name="Fit whole map").click()
        expect(page.locator("#world")).to_have_attribute("transform", "translate(0 0) scale(1)")
        page.get_by_role("button", name="Zoom in", exact=True).click()
        expect(page.locator("#world")).to_have_attribute(
            "transform", "translate(-600 -387.5) scale(1.5)"
        )
        page.get_by_role("button", name="About this world").click()
        assert page.locator("#about").is_visible()
        page.keyboard.press("Escape")
        assert not page.locator("#about").is_visible()
        for width in (320, 390, 900, 1440):
            page.set_viewport_size({"width": width, "height": 900})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert not errors
        assert all(url.startswith("file:") for url in requests)
        browser.close()


def test_vector_preparation_preserves_world_and_density() -> None:
    from copy import deepcopy

    from scala_security.map_geometry import overview_curve, prepare_world, sparse_decor

    world = {
        "countries": [
            {"path": "M0,0 L10,0 10,10 0,10Z"},
            {"path": "M10,0 L20,0 20,10 10,10Z"},
        ],
        "decor": [["mountain", 30 * i, 50, 1] for i in range(8)],
        "land": [],
        "lakes": [],
        "rivers": [],
    }
    original = deepcopy(world)
    prepared = prepare_world(world)
    assert world == original
    assert prepared["decor_count"] == 4
    assert sum(len(b["paths"]) for b in prepared["scenery"]) == 3
    assert prepared == prepare_world(world)
    world["decor"] = sparse_decor(world)
    world["decor_density"] = 0.5
    assert len(sparse_decor(world)) == 4
    curve = "M0,0C10,0,20,0,30,0C30,1,20,1,0,1"
    reduced = overview_curve(curve)
    assert "C" not in reduced and reduced.startswith("M0.00,0.00")
    assert reduced.endswith("0.00,1.00")
    assert overview_curve("M0,0Q1,2,3,4") == "M0,0Q1,2,3,4"


def test_camera_batches_events_and_reuses_pan_labels(tmp_path: Path) -> None:
    database, world = map_fixture(tmp_path)
    output = tmp_path / "map.html"
    render_map(database, output, world)
    with sync_playwright() as p:
        browser = getattr(p, os.environ.get("MAP_TEST_BROWSER", "chromium")).launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.goto(output.as_uri())
        page.wait_for_function("document.querySelector('#world').hasAttribute('transform')")
        result = page.evaluate("""async () => {
          const world=document.querySelector('#world'), atlas=document.querySelector('#atlas');
          let writes=0;
          const observer=new MutationObserver(records=>writes+=records.length);
          observer.observe(world,{attributes:true,attributeFilter:['transform']});
          for(let i=0;i<10;i++)atlas.dispatchEvent(new WheelEvent('wheel',{
            deltaY:-10,clientX:500,clientY:400,bubbles:true,cancelable:true}));
          const immediate=world.getAttribute('transform');
          await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
          observer.disconnect();
          return {writes,immediate,final:world.getAttribute('transform')};
        }""")
        assert result["writes"] == 1
        assert result["immediate"] != result["final"]
        page.wait_for_timeout(150)
        page.mouse.move(500, 400)
        page.mouse.down()
        page.evaluate("""() => {
          window.labelMutations=0;
          window.labelObserver=new MutationObserver(r=>window.labelMutations+=r.length);
          window.labelObserver.observe(document.querySelector('#labels'),{subtree:true,attributes:true});
        }""")
        page.mouse.move(560, 420, steps=8)
        assert page.locator("#connections").evaluate("el=>el.style.visibility") == "hidden"
        assert page.locator("#scenery").is_visible()
        page.mouse.up()
        page.wait_for_timeout(200)
        assert page.evaluate("window.labelMutations") == 0
        assert page.locator("#connections").evaluate("el=>el.style.visibility") == ""
        assert page.locator("#compromised-count").inner_text() == "0"
        browser.close()
