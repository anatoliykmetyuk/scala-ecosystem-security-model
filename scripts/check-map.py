"""Offline smoke test and timings for an actual generated map HTML."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("html", type=Path)
    parser.add_argument("--output", type=Path, default=Path("output/map-verification"))
    parser.add_argument("--browser", choices=["chromium", "firefox"], default="chromium")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = getattr(p, args.browser).launch()
        context = browser.new_context(offline=True, viewport={"width": 1600, "height": 1000})
        page = context.new_page()
        errors, requests = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: requests.append(request.url))
        start = time.perf_counter()
        page.goto(args.html.resolve().as_uri())
        page.wait_for_function("document.documentElement.dataset.mapReady === 'true'")
        load_seconds = time.perf_counter() - start
        model = json.loads(page.locator("#map-data").text_content() or "{}")
        projects = model["projects"]
        assert page.locator(".country").count() == len(projects)
        page.screenshot(path=str(args.output / "overview.png"))
        chosen = sorted(range(len(projects)), key=lambda i: -projects[i]["exposure"])[:2]
        affected = set(chosen)
        for i in chosen:
            affected.update(j for j, _ in model["fallout"][i])
        interaction_times = []
        for i in chosen:
            page.get_by_label("Find a project").fill(projects[i]["id"])
            page.locator("#search-results").get_by_role(
                "button", name=projects[i]["id"], exact=True
            ).click()
            start = time.perf_counter()
            page.get_by_role("button", name="Compromise this project", exact=True).click()
            interaction_times.append(time.perf_counter() - start)
        assert int(page.locator("#compromised-count").inner_text()) == len(chosen)
        assert int(page.locator("#exposed-count").inner_text()) == len(affected) - len(chosen)
        expected_percent = f"{100 * len(affected) / len(projects):.1f}"
        assert page.locator("#affected-percent").inner_text() == expected_percent
        total_value = sum(p["value"] or 0 for p in projects)
        affected_value = sum(projects[i]["value"] or 0 for i in affected)
        assert (
            page.locator("#value-percent").inner_text()
            == f"{100 * affected_value / total_value:.1f}%"
        )
        page.get_by_role("button", name="Fit whole map").click()
        page.locator("aside").evaluate("el => el.scrollTop = 280")
        page.screenshot(path=str(args.output / "simulation.png"))
        # Check both detail levels on the actual geometry, including close-zoom artwork.
        for _ in range(3):
            page.get_by_role("button", name="Zoom in", exact=True).click()
        page.wait_for_function(
            "document.querySelector('#world').getAttribute('transform').includes('scale(3.375)')"
        )
        assert (
            page.locator("#water .river").evaluate_all("els=>els.map(e=>e.getAttribute('d'))")
            == model["world"]["rivers"]
        )
        page.screenshot(path=str(args.output / "close-zoom.png"))
        page.get_by_role("button", name="Fit whole map").click()
        page.wait_for_function(
            "document.querySelector('#world').getAttribute('transform') === 'translate(0 0) scale(1)'"
        )
        assert (
            page.locator("#water .river").evaluate_all("els=>els.map(e=>e.getAttribute('d'))")
            == model["world"]["overview"]["rivers"]
        )
        layer_times = []
        for name in ("security", "maintenance", "value", "exposure"):
            start = time.perf_counter()
            page.get_by_label("Map layer", exact=True).select_option(name)
            layer_times.append(time.perf_counter() - start)
            assert page.locator("#affected-percent").inner_text() == expected_percent
        # Use the interior anchor exported by Azgaar, not the bounding-box center
        # (which can be outside an irregular or island country's actual fill).
        selected = chosen[0]
        anchor = next(
            c for c in model["world"]["countries"] if c["project"] == projects[selected]["id"]
        )
        point = page.locator("#world").evaluate(
            "(el,p) => {const q=new DOMPoint(p.x,p.y).matrixTransform(el.getScreenCTM());return {x:q.x,y:q.y}}",
            anchor,
        )
        page.mouse.move(point["x"], point["y"])
        page.wait_for_function("document.querySelectorAll('#connections path').length > 0")
        count5 = page.locator("#connections path").count()
        assert count5 == len(model["fallout"][selected])
        page.locator("#hops").fill("1")
        page.mouse.move(point["x"] + 1, point["y"])
        count1 = page.locator("#connections path").count()
        assert count1 == sum(h <= 1 for _, h in model["fallout"][selected])
        assert page.locator("#affected-percent").inner_text() == expected_percent
        page.get_by_label("Hover connections", exact=True).uncheck()
        assert page.locator("#connections path").count() == 0
        # Dragging over a country must not accidentally compromise it.
        page.mouse.move(point["x"], point["y"])
        page.mouse.down()
        page.mouse.move(point["x"] + 70, point["y"] + 40, steps=8)
        page.mouse.up()
        assert int(page.locator("#compromised-count").inner_text()) == len(chosen)
        page.get_by_role("button", name="Fit whole map").click()
        zoom_start = time.perf_counter()
        page.get_by_role("button", name="Zoom in", exact=True).click()
        zoom_seconds = time.perf_counter() - zoom_start
        for viewport in ({"width": 390, "height": 844}, {"width": 1024, "height": 768}):
            page.set_viewport_size({"width": viewport["width"], "height": viewport["height"]})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.set_viewport_size({"width": 390, "height": 844})
        page.get_by_role("button", name="Fit whole map").click()
        page.screenshot(path=str(args.output / "mobile.png"), full_page=True)
        assert not errors, errors
        assert all(url.startswith("file:") for url in requests), requests
        metrics = {
            "browser": args.browser,
            "browser_version": browser.version,
            "projects": len(projects),
            "html_bytes": args.html.stat().st_size,
            "offline_load_seconds": round(load_seconds, 3),
            "compromise_action_seconds": [round(v, 3) for v in interaction_times],
            "layer_action_seconds": [round(v, 3) for v in layer_times],
            "zoom_action_seconds": round(zoom_seconds, 3),
            "external_requests": 0,
            "javascript_errors": errors,
            "tested_selection": [projects[i]["id"] for i in chosen],
            "affected_projects": len(affected),
            "hover_connections_5_hops": count5,
            "hover_connections_1_hop": count1,
            "note": "Single local browser smoke run; action timings include Playwright overhead and are not FPS measurements.",
        }
        (args.output / "verification.json").write_text(json.dumps(metrics, indent=2))
        print(json.dumps(metrics, indent=2))
        browser.close()


if __name__ == "__main__":
    main()
