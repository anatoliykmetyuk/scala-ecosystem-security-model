"""Offline browser regression for the generated standalone report."""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright
from test_pipeline import fixture_db

from scala_security.analyze import analyze
from scala_security.render import render


def test_report_interactions_and_math(tmp_path: Path) -> None:
    db = fixture_db(tmp_path / "db.sqlite")
    for kind, payload in {
        "repository": {"pushed_at": "2025-01-01", "last_synced_at": "2026-09-01"},
        "commits": {
            "last_synced_at": "2026-09-01",
            "past_year_committers": [{"name": "Human", "count": 10}],
        },
        "scorecard": {
            "date": "2026-09-01",
            "checks": [
                {"name": name, "score": 5, "reason": "Fixture observation"}
                for name in (
                    "Code-Review",
                    "Branch-Protection",
                    "Token-Permissions",
                    "Dangerous-Workflow",
                    "Pinned-Dependencies",
                    "Security-Policy",
                    "Vulnerabilities",
                    "SAST",
                )
            ],
        },
    }.items():
        db.execute(
            "INSERT INTO observations VALUES(?,?,?,?)",
            ("scala/b", kind, json.dumps(payload), "https://example.test/evidence"),
        )
    db.execute(
        "INSERT INTO metadata VALUES('target_matrix',?)",
        (
            json.dumps(
                {
                    "jvm": {"scala": ["2.13", "3"]},
                    "sbt": {
                        "variants": [{"scala": "2.12", "sbt": "1.0"}, {"scala": "3", "sbt": "2"}]
                    },
                }
            ),
        ),
    )
    analyze(db)
    report = tmp_path / "preview.html"
    render(db, report)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(offline=True)
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(report.as_uri())
        assert page.locator("math").count() >= 9
        panels = page.locator("details.calculation")
        assert panels.count() == 3
        for panel, symbol in zip(panels.all(), ("R", "S", "V")):
            assert panel.get_attribute("open") is None
            assert not panel.locator("math").first.is_visible()
            panel.locator("summary").click()
            assert panel.locator("math").first.is_visible()
            assert symbol in panel.locator(".symbols").inner_text()
            assert panel.evaluate(
                "el => Boolean(el.querySelector('.symbols').compareDocumentPosition(el.querySelector('math')) & Node.DOCUMENT_POSITION_FOLLOWING)"
            )
            panel.locator("summary").click()
            assert not panel.locator("math").first.is_visible()

        assert "0.20" in page.locator(".metrics").inner_text()
        assert "0.50" in page.locator(".metrics").inner_text()
        assert page.locator("math").filter(has_text="0.3333").count() >= 1
        for slug in ("metric-contributors", "metric-contributor-absence-factor"):
            source = page.locator(f'.symbols a[href="https://www.chaoss.community/kb/{slug}/"]')
            assert source.count() == 1
            assert source.get_attribute("target") == "_blank"
        assert "not prescribed by CHAOSS" in (panels.first.text_content() or "")
        assert page.locator("select").count() == 0
        assert "jvm · Scala 2.13, 3" in page.locator("#matrix").inner_text()
        assert "sbt · Scala 2.12 / sbt 1.0, Scala 3 / sbt 2" in page.locator("#matrix").inner_text()
        assert not page.locator("#about").is_visible()
        page.locator("#about-open").click()
        assert page.locator("#about").is_visible()
        page.keyboard.press("Escape")
        assert not page.locator("#about").is_visible()
        assert page.locator("#about-open").evaluate("el => el === document.activeElement")
        page.locator("#about-open").click()
        page.locator("#about-close").click()
        assert not page.locator("#about").is_visible()
        assert "Maximum 5 dependency hops" in page.locator("#about").inner_text()
        page.locator(".beneficiary-head .number").first.click()
        assert page.locator(".path").first.is_visible()
        page.get_by_role("button", name="Hide path").first.click()
        assert not page.locator(".path").first.is_visible()
        link = page.locator(".beneficiary-head a").first
        assert link.get_attribute("target") == "_blank"
        context.route("https://github.com/**", lambda route: route.fulfill(body="repository"))
        with page.expect_popup() as popup:
            link.click()
        popup.value.close()
        assert not page.locator(".path").first.is_visible()
        page.locator("#search").fill("scala/c")
        assert page.locator(".rank-button").count() == 1
        page.locator(".rank-button").click()
        assert "scala/c" in page.locator("#detail h2").inner_text()
        for theme in ("light", "dark"):
            page.emulate_media(color_scheme=theme)
            for width in (360, 1024):
                page.set_viewport_size({"width": width, "height": 900})
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert not errors
        browser.close()
