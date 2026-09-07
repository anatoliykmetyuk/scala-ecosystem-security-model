"""Offline browser regression for the generated standalone report."""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright
from test_pipeline import fixture_db

from scala_security.analyze import analyze
from scala_security.render import render


def test_report_interactions_and_math(tmp_path: Path) -> None:
    db = fixture_db(tmp_path / "db.sqlite")
    analyze(db)
    report = tmp_path / "preview.html"
    render(db, report)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(report.as_uri())
        assert page.locator("math").count() >= 3
        assert page.locator("select").count() == 0
        assert "Maximum 3 dependency hops" in page.locator("header").inner_text()
        toggle = page.get_by_role("button", name="Show path").first
        toggle.click()
        assert page.locator(".path").first.is_visible()
        page.get_by_role("button", name="Hide path").first.click()
        assert not page.locator(".path").first.is_visible()
        link = page.locator(".beneficiary-head a").first
        assert link.get_attribute("target") == "_blank"
        page.route("https://github.com/**", lambda route: route.fulfill(body="repository"))
        with page.expect_popup() as popup:
            link.click()
        popup.value.close()
        assert not page.locator(".path").first.is_visible()
        page.locator("#search").fill("scala/c")
        assert page.locator(".rank-button").count() == 1
        page.locator(".rank-button").click()
        assert "scala/c" in page.locator("h2").inner_text()
        for theme in ("light", "dark"):
            page.emulate_media(color_scheme=theme)
            for width in (360, 1024):
                page.set_viewport_size({"width": width, "height": 900})
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert not errors
        browser.close()
