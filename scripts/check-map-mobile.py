"""Offline mobile layout and real multi-touch input regression checks."""

import re
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 390, "height": 844}, has_touch=True)
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(Path(sys.argv[1]).resolve().as_uri())
    page.wait_for_function("document.documentElement.dataset.mapReady === 'true'")
    for width, height in [(320, 568), (375, 667), (390, 844), (700, 500)]:
        page.set_viewport_size({"width": width, "height": height})
        boxes = [
            page.locator(s).bounding_box()
            for s in ["#mobile-options-toggle", "#compromise-mode", ".zoom"]
        ]
        assert all(b and b["x"] >= 0 and b["x"] + b["width"] <= width for b in boxes)
        assert max(b["y"] for b in boxes) - min(b["y"] for b in boxes) < 8
        assert not page.locator(".legend").is_visible()
    page.set_viewport_size({"width": 390, "height": 844})
    page.locator("#mobile-options-toggle").click()
    expect(page.locator(".legend")).to_be_visible()
    page.locator('[data-layer="security"]').click()
    page.keyboard.press("Escape")
    assert not page.locator(".legend").is_visible()
    page.locator("#compromise-mode").click()
    page.locator('.country[aria-label="zio/zio"]').click()
    assert page.locator("#shared-exposure").bounding_box()["height"] < 90
    assert not page.locator("#impact-details").is_visible()
    page.locator("#impact-toggle").click()
    assert page.locator("#impact-details").is_visible()
    page.locator("#impact-toggle").click()
    page.locator("#reset").click()
    assert not page.locator("#shared-exposure").is_visible()

    cdp = page.context.new_cdp_session(page)

    def touch(kind, points):
        cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": points})

    def points(distance):
        return [
            {"x": 195 - distance / 2, "y": 430, "id": 1},
            {"x": 195 + distance / 2, "y": 430, "id": 2},
        ]

    def scale():
        return float(
            re.search(r"scale\(([^)]+)", page.locator("#world").get_attribute("transform"))[1]
        )

    touch("touchStart", points(80))
    for d in range(100, 201, 20):
        touch("touchMove", points(d))
    page.wait_for_function(
        r'Number(document.querySelector("#world").getAttribute("transform").match(/scale\(([^)]+)/)[1]) > 2.3'
    )
    assert 2.3 < scale() < 2.7
    for d in range(180, 79, -20):
        touch("touchMove", points(d))
    touch("touchEnd", [])
    page.wait_for_function(
        r'Number(document.querySelector("#world").getAttribute("transform").match(/scale\(([^)]+)/)[1]) < 1.1'
    )
    assert not page.locator("#shared-exposure").is_visible(), "Pinch must not compromise a country"
    page.locator("#zoom-in").click()
    page.wait_for_function(
        'document.querySelector("#world").getAttribute("transform").includes("scale(1.5)")'
    )
    before = page.locator("#world").get_attribute("transform")
    touch("touchStart", [{"x": 195, "y": 430, "id": 1}])
    touch("touchMove", [{"x": 225, "y": 450, "id": 1}])
    touch("touchEnd", [])
    page.wait_for_function(
        "(before)=>document.querySelector('#world').getAttribute('transform')!==before", arg=before
    )
    assert scale() == 1.5
    page.set_viewport_size({"width": 1440, "height": 900})
    assert not page.locator("#mobile-options-toggle").is_visible()
    expect(page.locator(".legend")).to_be_visible()
    assert page.locator("#show-scenery").is_visible()
    assert page.locator('[data-layer="security"]').get_attribute("aria-pressed") == "true"
    assert not errors, errors
    browser.close()
    print("Mobile layout, menu, impact summary, pinch in/out, pan, and desktop restoration passed.")
