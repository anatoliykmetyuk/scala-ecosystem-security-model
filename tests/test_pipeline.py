from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from scala_security.analyze import analyze, validate
from scala_security.collect import Collector, dependencies, exact
from scala_security.data import JSON, connect, repo_name
from scala_security.http import Fetcher, query
from scala_security.render import render
from scala_security.scoring import health, value


def fixture_db(path: Path):
    db = connect(path)
    db.execute("INSERT INTO metadata VALUES('collected_at','2026-09-07T00:00:00+00:00')")
    for project, stars, seed, latest in [
        ("scala/c", 100, 1, "1"),
        ("scala/b", 1000, 1, "2"),
        ("java/a", 500, 0, "3"),
    ]:
        db.execute(
            "INSERT INTO projects(id,stars,seed,latest) VALUES(?,?,?,?)",
            (project, stars, seed, latest),
        )
    for name, project in [
        ("g:c_3", "scala/c"),
        ("g:b_3", "scala/b"),
        ("g:a", "java/a"),
        ("g:a_2.12", "java/a"),
    ]:
        db.execute("INSERT INTO artifacts(id,project) VALUES(?,?)", (name, project))
    for artifact, version in [
        ("g:c_3", "1"),
        ("g:b_3", "1"),
        ("g:b_3", "2"),
        ("g:a", "3"),
        ("g:a_2.12", "1"),
    ]:
        db.execute(
            "INSERT INTO versions VALUES(?,?,?,1)", (artifact + "@" + version, artifact, version)
        )
    for source, target, scope in [
        ("g:b_3@2", "g:c_3@1", "compile"),
        ("g:a@3", "g:b_3@1", "test"),
        ("g:a_2.12@1", "g:c_3@1", "compile"),
    ]:
        db.execute(
            "INSERT INTO edges(source,target,scope,optional,exact,evidence) VALUES(?,?,?,0,1,?)",
            (source, target, scope, "https://repo.maven.apache.org/test.pom"),
        )
    db.commit()
    return db


def test_fallout_latest_crossbuild_and_java_consumer(tmp_path):
    db = fixture_db(tmp_path / "model.sqlite")
    analyze(db)
    assert set(map(tuple, db.execute("SELECT * FROM fallout"))) == {
        ("scala/c", "scala/b"),
        ("scala/b", "java/a"),
    }
    assert (
        db.execute("SELECT count(*) FROM ranking WHERE project=?", ("java/a",)).fetchone()[0] == 0
    )
    assert validate(db)["fallout"] == 2
    assert (
        float(db.execute("SELECT value FROM metadata WHERE key='traversal_seconds'").fetchone()[0])
        >= 0
    )
    render(db, tmp_path / "preview.html")
    html = (tmp_path / "preview.html").read_text()
    assert "<math " in html and "Show path" in html
    assert "fetch(" not in html and "__DATA__" not in html


def test_versions_connect_transitively_and_deduplicate(tmp_path):
    db = fixture_db(tmp_path / "model.sqlite")
    db.execute(
        "INSERT INTO edges(source,target,scope,optional,exact) VALUES('g:b_3@1','g:c_3@1','runtime',0,1)"
    )
    analyze(db)
    assert (
        db.execute(
            "SELECT count(*) FROM fallout WHERE target='scala/c' AND dependant='java/a'"
        ).fetchone()[0]
        == 1
    )
    v1, v2 = value(1000), value(500)
    assert v1 is not None and v2 is not None
    expected = v1 + v2
    assert db.execute("SELECT exposure FROM ranking WHERE project='scala/c'").fetchone()[
        0
    ] == pytest.approx(expected)
    assert validate(db)["fallout"] == 3


def test_http_pagination_cache_and_fresh_run(tmp_path):
    calls = []

    def handle(request):
        calls.append(str(request.url))
        page = int(request.url.params.get("page", "1"))
        return httpx.Response(200, json=[{"name": str(page)}] if page < 3 else [])

    transport = httpx.MockTransport(handle)
    fetch = Fetcher(tmp_path / "run1", transport)
    url = "https://example.test/items"
    assert len(fetch.pages(url)) == 2
    assert len(fetch.pages(url)) == 2
    assert len(calls) == 3  # cached pages include terminal empty page
    assert len(Fetcher(tmp_path / "run2", transport).pages(url)) == 2
    assert len(calls) == 6
    assert list((tmp_path / "run1").glob("*.json.gz"))


def test_repeated_page_is_a_gap(tmp_path):
    fetch = Fetcher(
        tmp_path, httpx.MockTransport(lambda r: httpx.Response(200, json=[{"name": "same"}]))
    )
    assert len(fetch.pages("https://example.test/items")) == 1
    assert any("Repeated page" in message for _, message in fetch.failures)


def test_pom_overrides_and_missing_direct_declarations():
    pom = """<project><version>2</version><properties><dep.version>1</dep.version></properties><dependencies>
    <dependency><groupId>g</groupId><artifactId>b</artifactId><version>${dep.version}</version><scope>test</scope><optional>true</optional></dependency>
    <dependency><groupId>g</groupId><artifactId>c</artifactId><version>3</version></dependency></dependencies></project>"""
    deps = dependencies(
        {
            "dependencies": [
                {
                    "package_name": "g:b",
                    "requirements": "${dep.version}",
                    "kind": "runtime",
                    "optional": False,
                }
            ]
        },
        pom,
    )
    assert (
        deps[0]["kind"] == "test" and deps[0]["optional"] is True and deps[0]["requirements"] == "1"
    )
    assert deps[1]["kind"] == "compile"
    assert not exact("[1,2)") and not exact("${version}") and exact("1.0-RC1")


def test_inherited_defaults_are_not_invented():
    deps = dependencies(
        {},
        "<project><parent/><dependencies><dependency><groupId>g</groupId><artifactId>b</artifactId><version>1</version></dependency></dependencies></project>",
    )
    assert deps[0]["kind"] is None and deps[0]["optional"] is None


def test_scores_missing_bot_filter_and_renormalization():
    now = datetime(2026, 9, 7, tzinfo=timezone.utc)
    commits: dict[str, JSON] = {
        "last_synced_at": "2026-09-01",
        "past_year_committers": [
            {"login": "dependabot[bot]", "count": 1000},
            {"login": "a", "count": 6},
            {"login": "b", "count": 4},
        ],
    }
    result = health({}, commits, {}, now)
    assert result.humans == 2 and result.absence_factor == 1
    assert result.maintenance == pytest.approx((0.35 * 0.4 + 0.4 / 3) / 0.75)
    assert result.security is None
    assert health({}, {}, {}, now).maintenance is None
    assert value(None) is None and value(0) == 0 and value(100000) == 1
    archived = health({"archived": True, "last_synced_at": "2026-09-01"}, {}, {}, now)
    assert archived.maintenance == 0


def test_reverse_discovery_uses_historical_intermediates(tmp_path):
    urls = []

    def handler(request):
        urls.append(str(request.url))
        if request.url.params.get("page") == "2":
            return httpx.Response(200, json=[])
        name = (
            "g:b" if "/g:c/" in request.url.path else "g:a" if "/g:b/" in request.url.path else ""
        )
        return httpx.Response(
            200,
            json=[{"name": name, "repository_url": "https://github.com/java/" + name[-1]}]
            if name
            else [],
        )

    db = connect(tmp_path / "db.sqlite")
    c = Collector(db, Fetcher(tmp_path / "evidence", httpx.MockTransport(handler)))
    c.package({"name": "g:c"}, "scala/c")
    found = c.discover(["g:c"])
    assert {"g:a", "g:b", "g:c"} <= found
    assert any("g:c/dependent_packages?latest=false" in u for u in urls)
    assert any("g:b/dependent_packages?latest=false" in u for u in urls)
    assert any("g:a/dependent_packages?latest=true" in u for u in urls)


def test_latest_project_release_discards_old_artifact(tmp_path):
    fetch = Fetcher(
        tmp_path / "evidence",
        httpx.MockTransport(
            lambda r: httpx.Response(
                200, json=[{"groupId": "g", "artifactId": "a_3", "version": "2"}]
            )
        ),
    )
    c = Collector(connect(tmp_path / "db.sqlite"), fetch)
    project, latest, _ = c.release("scala/a")
    assert project == "scala/a" and latest == [
        {"groupId": "g", "artifactId": "a_3", "version": "2"}
    ]
    assert repo_name("https://github.com/Scala/A.git") == "scala/a"
    assert repo_name("https://notgithub.com/scala/a") == ""
    assert query("https://x.test/a?latest=false", page=2).endswith("latest=false&page=2")


def test_offline_collection_to_preview(tmp_path):
    def handler(request):
        path = request.url.path
        if path.endswith("/artifacts"):
            return httpx.Response(200, json=[{"groupId": "g", "artifactId": "c_3", "version": "1"}])
        if path.endswith("/versions/latest"):
            artifact = "c_3" if "/scala/c/" in path else "b_3"
            return httpx.Response(
                200, json=[{"groupId": "g", "artifactId": artifact, "version": "1"}]
            )
        if path.endswith("/dependent_packages"):
            return httpx.Response(
                200,
                json=[
                    {
                        "name": "g:b_3",
                        "repository_url": "https://github.com/scala/b",
                        "repo_metadata": {"stargazers_count": 100},
                    }
                ]
                if "g:c_3/" in path and request.url.params.get("page") == "1"
                else [],
            )
        if "/versions/1" in path:
            return httpx.Response(
                200,
                json={
                    "number": "1",
                    "dependencies": [
                        {
                            "package_name": "g:c_3",
                            "requirements": "1",
                            "kind": "compile",
                            "optional": False,
                        }
                    ],
                }
                if "g:b_3/" in path
                else {"number": "1", "dependencies": []},
            )
        if path.endswith(".pom"):
            return httpx.Response(200, text="<project/>")
        return httpx.Response(404, json={})

    db = connect(tmp_path / "snapshot.sqlite")
    Collector(db, Fetcher(tmp_path / "evidence", httpx.MockTransport(handler))).run(
        [{"repository": "scala/c", "categories": ["testing"], "artifacts": ["g:c_3"]}]
    )
    analyze(db)
    assert validate(db)["fallout"] == 1
    render(db, tmp_path / "preview.html")
    assert db.execute("SELECT exposure FROM ranking WHERE project='scala/c'").fetchone()[
        0
    ] == pytest.approx(value(100))
    assert (tmp_path / "preview.html").exists()


def test_three_hops_cycles_and_nested_test_exclusion(tmp_path):
    from scala_security.graph import paths

    db = connect(tmp_path / "db.sqlite")
    for name in ("a", "b", "c", "d", "e", "test"):
        db.execute("INSERT INTO projects(id) VALUES(?)", (name,))
        db.execute("INSERT INTO artifacts(id,project) VALUES(?,?)", (name, name))
        db.execute("INSERT INTO versions VALUES(?,?,?,1)", (name + "@1", name, "1"))
    for a, b, scope in [
        ("a", "b", "test"),
        ("b", "c", "runtime"),
        ("c", "d", "compile"),
        ("d", "e", "compile"),
        ("b", "a", "compile"),
        ("b", "test", "test"),
    ]:
        db.execute(
            "INSERT INTO edges(source,target,scope,optional,exact) VALUES(?,?,?,0,1)",
            (a + "@1", b + "@1", scope),
        )
    found = paths(db, ["a@1"])
    assert {"b", "c", "d"} <= found.keys()
    assert "e" not in found and "test" not in found
    assert len(found["d"]) == 3


def test_security_coverage_staleness_and_unavailable_check():
    from scala_security.scoring import SECURITY_WEIGHTS

    checks = [{"name": k, "score": 10} for k in SECURITY_WEIGHTS]
    checks[0]["score"] = -1
    now = datetime(2026, 9, 7, tzinfo=timezone.utc)
    current = health({}, {}, {"date": "2026-09-01", "checks": checks}, now)
    assert current.security == 1 and current.security_coverage < 1
    assert health({}, {}, {"date": "2025-01-01", "checks": checks}, now).security is None


def test_seed_selection_uses_all_variants_and_filters_java(tmp_path):
    import yaml

    from scala_security.seeds import select

    def handler(request):
        path = request.url.path
        if path == "/awesome":
            return httpx.Response(200, text='<a href="/awesome/testing?sort=stars">Testing</a>')
        if path == "/awesome/testing":
            return httpx.Response(
                200,
                text='<ol class="list-result"><li><a href="/java/only">J</a></li><li><a href="/scala/good">S</a></li></ol>'
                if request.url.params.get("page") == "1"
                else "",
            )
        if path.endswith("/languages"):
            return httpx.Response(
                200, json={"Java": 100} if "/java/" in path else {"Scala": 100, "Java": 10}
            )
        return httpx.Response(
            200,
            json=[
                {"groupId": "g", "artifactId": "good_3", "version": "2"},
                {"groupId": "g", "artifactId": "good_2.12", "version": "1"},
            ],
        )

    # Empty category page is valid HTML, not a transport failure.
    def wrapped(request):
        response = handler(request)
        return httpx.Response(200, text="<html></html>") if response.text == "" else response

    select(Fetcher(tmp_path / "evidence", httpx.MockTransport(wrapped)), tmp_path / "seeds.yaml")
    config = yaml.safe_load((tmp_path / "seeds.yaml").read_text())
    assert [p["repository"] for p in config["projects"]] == ["scala/good"]
    assert config["projects"][0]["artifacts"] == ["g:good_2.12", "g:good_3"]
    assert config["exclusions"][0]["project"] == "java/only"


def test_ambiguous_ownership_reconciled(tmp_path):
    fetch = Fetcher(
        tmp_path / "evidence",
        httpx.MockTransport(
            lambda r: httpx.Response(200, json={"repository_url": "https://github.com/scala/new"})
        ),
    )
    db = connect(tmp_path / "db.sqlite")
    collector = Collector(db, fetch)
    collector.package({"name": "g:shared_3"}, "scala/old")
    collector.package({"name": "g:other_3"}, "scala/new")
    collector.claims = {"g:shared_3": {"scala/old", "scala/new"}}
    collector.reconcile_ownership()
    assert (
        db.execute("SELECT project FROM artifacts WHERE id='g:shared_3'").fetchone()[0]
        == "scala/new"
    )


def test_concurrent_collectors_write_cache_atomically(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"ok": True}))
    left, right = Fetcher(tmp_path, transport), Fetcher(tmp_path, transport)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(f.json, "https://example.test/shared") for f in (left, right)]
        assert all(f.result() == {"ok": True} for f in futures)
    assert left.json("https://example.test/shared") == {"ok": True}
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("payload", [b"partial", b"\x1f\x8b\x08\x00" + b"\0" * 6 + b"\xff" * 10])
def test_corrupt_cache_recovers(tmp_path, payload):
    fetch = Fetcher(tmp_path, httpx.MockTransport(lambda r: httpx.Response(200, json={"ok": True})))
    url = "https://example.test/broken"
    fetch.path(url).write_bytes(payload)
    assert fetch.json(url) == {"ok": True}
    assert list(tmp_path.glob("*.corrupt"))


def test_star_selection_does_not_depend_on_fetch_completion_order(tmp_path):
    metadata = [
        {"stargazers_count": 80, "last_synced_at": "2026-08-01"},
        {"stargazers_count": 50, "last_synced_at": "2026-09-01"},
    ]
    for i, observations in enumerate((metadata, list(reversed(metadata)))):
        collector = Collector(
            connect(tmp_path / f"{i}.sqlite"),
            Fetcher(tmp_path / f"e{i}", httpx.MockTransport(lambda r: httpx.Response(200))),
        )
        for j, m in enumerate(observations):
            collector.package(
                {
                    "name": f"g:artifact{j}",
                    "repository_url": "https://github.com/scala/a",
                    "repo_metadata": m,
                }
            )
        assert (
            collector.db.execute("SELECT stars FROM projects WHERE id='scala/a'").fetchone()[0]
            == 50
        )


def test_contact_header_scoped_to_ecosystems(tmp_path, monkeypatch):
    monkeypatch.setenv("ECOSYSTEMS_CONTACT_EMAIL", "contact@example.test")
    observed = {}

    def handle(request):
        observed[request.url.host] = request.headers.get("from")
        return httpx.Response(200, json=[])

    fetch = Fetcher(tmp_path, httpx.MockTransport(handle))
    for host in ("packages.ecosyste.ms", "api.github.com", "ecosyste.ms.example.test"):
        fetch.json("https://" + host + "/items")
    assert observed == {
        "packages.ecosyste.ms": "contact@example.test",
        "api.github.com": None,
        "ecosyste.ms.example.test": None,
    }


def test_unresolved_ownership_stays_unattributed(tmp_path):
    fetch = Fetcher(
        tmp_path / "evidence",
        httpx.MockTransport(
            lambda r: httpx.Response(
                200, json={"repository_url": "https://github.com/unrelated/repo"}
            )
        ),
    )
    db = connect(tmp_path / "db.sqlite")
    collector = Collector(db, fetch)
    collector.package({"name": "g:shared_3"}, "scala/old")
    collector.claims = {"g:shared_3": {"scala/old", "scala/new"}}
    collector.reconcile_ownership()
    collector.package({"name": "g:shared_3", "repository_url": "https://github.com/unrelated/repo"})
    assert db.execute("SELECT project FROM artifacts").fetchone()[0] is None


def test_active_pom_build_inputs_are_included():
    from scala_security.collect import pom_dependencies

    pom = """<project><build>
      <plugins><plugin><artifactId>maven-compiler-plugin</artifactId><version>3.14.0</version></plugin></plugins>
      <extensions><extension><groupId>g</groupId><artifactId>extension</artifactId><version>1</version></extension></extensions>
      <pluginManagement><plugins><plugin><artifactId>inactive-plugin</artifactId><version>1</version></plugin></plugins></pluginManagement>
    </build></project>"""
    found = pom_dependencies(pom)
    assert {d["package_name"] for d in found} == {
        "org.apache.maven.plugins:maven-compiler-plugin",
        "g:extension",
    }
    assert all(d["kind"] == "build" and d["optional"] is False for d in found)
