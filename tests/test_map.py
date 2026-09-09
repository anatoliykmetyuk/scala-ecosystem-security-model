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


def test_search_arrow_selection_and_map_placement(tmp_path: Path) -> None:
    database, world = map_fixture(tmp_path)
    output = tmp_path / "map.html"
    render_map(database, output, world)
    with sync_playwright() as p:
        browser = getattr(p, os.environ.get("MAP_TEST_BROWSER", "chromium")).launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.goto(output.as_uri())
        search = page.get_by_role("combobox", name="Find a project")
        assert page.locator(".map-stage #search").count() == 1
        assert page.locator("aside #search, .map-top").count() == 0
        search.fill("/")
        for key, name in (
            ("ArrowDown", "java/a"),
            ("ArrowDown", "scala/b"),
            ("ArrowDown", "scala/c"),
            ("ArrowUp", "scala/b"),
        ):
            search.press(key)
            expect(page.get_by_role("option", name=name, exact=True)).to_have_attribute(
                "aria-selected", "true"
            )
            expect(search).to_be_focused()
            assert page.locator('[role="option"][aria-selected="true"]').count() == 1
        search.press("Enter")
        expect(page.locator("#project-detail .owner")).to_have_text("scala/b")
        expect(search).to_have_attribute("aria-expanded", "false")
        assert page.locator("#compromised-count").inner_text() == "0"
        expect(search).to_be_visible()  # Search remains available after flying to a country.
        search.fill("/")
        search.press("ArrowUp")
        expect(page.get_by_role("option", name="scala/c", exact=True)).to_have_attribute(
            "aria-selected", "true"
        )
        search.press("Escape")
        expect(search).to_have_attribute("aria-expanded", "false")
        assert search.get_attribute("aria-activedescendant") is None
        search.press("ArrowDown")
        expect(page.get_by_role("option", name="java/a", exact=True)).to_have_attribute(
            "aria-selected", "true"
        )
        search.fill("no-such-project")
        search.press("ArrowDown")
        search.press("Enter")
        expect(page.locator("#project-detail .owner")).to_have_text("scala/b")
        search.fill("/")
        page.get_by_role("option", name="scala/c", exact=True).click()
        expect(page.locator("#project-detail .owner")).to_have_text("scala/c")
        for width in (320, 390, 1440):
            page.set_viewport_size({"width": width, "height": 900})
            search.fill("/")
            box = page.locator("#search-results").bounding_box()
            assert box and box["x"] >= 0 and box["x"] + box["width"] <= width
        browser.close()


def test_map_detail_buttons_and_all_hop_connections(tmp_path: Path) -> None:
    database, world = map_fixture(tmp_path)
    output = tmp_path / "map.html"
    render_map(database, output, world)
    model = read_snapshot(database)
    target = next(i for i, project in enumerate(model["projects"]) if project["id"] == "scala/c")
    with sync_playwright() as p:
        browser = getattr(p, os.environ.get("MAP_TEST_BROWSER", "chromium")).launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.goto(output.as_uri())
        scenery = page.get_by_role("button", name="Scenery", exact=True)
        links = page.get_by_role("button", name="Hover connections", exact=True)
        expect(scenery).to_have_attribute("aria-pressed", "true")
        expect(links).to_have_attribute("aria-pressed", "false")
        assert page.locator("#hops, input[type=checkbox]").count() == 0
        assert page.locator(".map-controls #show-scenery, .map-controls #show-links").count() == 2
        page.locator(f"#country-{target}").dispatch_event(
            "pointerenter", {"clientX": 500, "clientY": 400}
        )
        assert page.locator("#connections path").count() == 0
        scenery.click()
        assert page.locator("#scenery").evaluate("el=>el.style.display") == "none"
        scenery.focus()
        page.keyboard.press("Space")
        expect(scenery).to_have_attribute("aria-pressed", "true")
        assert page.locator("#scenery").evaluate("el=>el.style.display") == ""
        links.focus()
        page.keyboard.press("Enter")
        expect(links).to_have_attribute("aria-pressed", "true")
        page.locator(f"#country-{target}").dispatch_event(
            "pointerenter", {"clientX": 500, "clientY": 400}
        )
        assert page.locator("#connections path").count() == len(model["fallout"][target])
        links.click()
        assert page.locator("#connections path").count() == 0
        for width in (320, 390, 1440):
            page.set_viewport_size({"width": width, "height": 900})
            for selector in (
                "#show-scenery",
                "#show-links",
                '[data-layer="exposure"]',
                "#zoom-fit",
            ):
                box = page.locator(selector).bounding_box()
                assert box and box["x"] >= 0 and box["x"] + box["width"] <= width
        browser.close()


def test_inspection_compromise_mode_and_conditional_overlays(tmp_path: Path) -> None:
    database, world = map_fixture(tmp_path)
    output = tmp_path / "map.html"
    render_map(database, output, world)
    model = read_snapshot(database)
    ids = {project["id"]: i for i, project in enumerate(model["projects"])}
    with sync_playwright() as p:
        browser = getattr(p, os.environ.get("MAP_TEST_BROWSER", "chromium")).launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.goto(output.as_uri())
        panel, summary = page.locator("#project-panel"), page.locator("#shared-exposure")
        mode = page.get_by_role("button", name="Compromise mode", exact=True)
        expect(panel).to_be_hidden()
        expect(summary).to_be_hidden()
        expect(mode).to_have_attribute("aria-pressed", "false")
        assert page.locator("#atlas").bounding_box() == {
            "x": 0,
            "y": 0,
            "width": 1440,
            "height": 1000,
        }
        page.locator(f"#country-{ids['scala/c']}").dispatch_event("click")
        expect(panel).to_be_visible()
        expect(page.get_by_role("combobox")).to_have_value("scala/c")
        assert page.locator("#compromised-count").inner_text() == "0"
        expect(summary).to_be_hidden()
        page.locator(f"#country-{ids['scala/b']}").dispatch_event("click")
        expect(page.locator("#project-detail .owner")).to_have_text("scala/b")
        page.mouse.click(900, 40)  # Open map space, outside both overlays.
        expect(panel).to_be_hidden()
        expect(page.get_by_role("combobox")).to_have_value("")
        page.locator(f"#country-{ids['scala/c']}").dispatch_event("click")
        page.get_by_role("button", name="Compromise this project", exact=True).click()
        expect(summary).to_be_visible()
        expect(panel).to_be_visible()
        assert page.locator("#compromised-count").inner_text() == "1"
        assert page.locator("#exposed-count").inner_text() == "1"
        mode.click()
        expect(panel).to_be_hidden()
        expect(page.get_by_role("combobox")).to_have_value("")
        assert page.locator(".country.focused").count() == 0
        page.locator(f"#country-{ids['scala/b']}").dispatch_event("click")
        expect(panel).to_be_hidden()
        assert page.locator("#compromised-count").inner_text() == "2"
        assert page.locator("#affected-percent").inner_text() == "100.0"
        # Clicking again in compromise mode undoes that compromise, without selecting.
        page.locator(f"#country-{ids['scala/b']}").dispatch_event("click")
        assert page.locator("#compromised-count").inner_text() == "1"
        mode.click()
        page.locator(f"#country-{ids['scala/b']}").dispatch_event("click")
        expect(panel).to_be_visible()
        assert page.locator("#compromised-count").inner_text() == "1"
        page.get_by_role("button", name="Reset", exact=True).click()
        expect(summary).to_be_hidden()
        expect(panel).to_be_visible()
        page.get_by_role("button", name="Close project details", exact=True).click()
        expect(panel).to_be_hidden()
        mode.click()
        search = page.get_by_role("combobox")
        search.fill("scala/c")
        search.press("Enter")
        expect(panel).to_be_visible()
        expect(search).to_have_value("scala/c")
        expect(mode).to_have_attribute("aria-pressed", "false")
        page.get_by_role("button", name="Compromise this project", exact=True).click()
        for width in (320, 390, 900, 1440):
            page.set_viewport_size({"width": width, "height": 844})
            assert page.locator("#atlas").bounding_box()["width"] == width
            for overlay in (panel, summary):
                box = overlay.bounding_box()
                assert box and box["x"] >= 0 and box["x"] + box["width"] <= width
                assert box["y"] >= 0 and box["y"] + box["height"] <= 844
        browser.close()
