"""Offline seed schema, selection limits and matrix-boundary regressions."""

from pathlib import Path

import httpx
import pytest
import yaml
from test_pipeline import fixture_db

from scala_security.analyze import analyze, validate
from scala_security.collect import Collector
from scala_security.configuration import (
    DEFAULT_MATRIX,
    excluded_repository,
    expand,
    modules_for,
    parse_config,
)
from scala_security.data import JSON, connect, string
from scala_security.http import Fetcher
from scala_security.seeds import choose_projects, main_sections


def document(repo="scala/subject"):
    return {
        "schema": 2,
        "matrix": DEFAULT_MATRIX,
        "projects": [{"repository": repo, "categories": ["Testing"], "modules": ["g:subject"]}],
    }


def test_matrix_expansion_and_module_extraction():
    assert expand(["org.scala-graph:graph-core"], DEFAULT_MATRIX) == [
        "org.scala-graph:graph-core_2.13",
        "org.scala-graph:graph-core_3",
    ]
    assert modules_for(
        [
            "g:a_2.13",
            "g:a_3",
            "g:a_native0.5_3",
            "g:b_sjs1_3",
            "g:c_2.12",
            "g:d_2.13.16",
            "g:plain",
            "g:spark_3.0_2.13",
        ],
        DEFAULT_MATRIX,
    ) == ["g:a", "g:spark_3.0"]
    assert expand(
        ["g:a"],
        {
            "scala_native": {"versions": ["0.5"], "scala": ["3"]},
            "scala_js": {"versions": ["1"], "scala": ["2.13"]},
        },
    ) == ["g:a_native0.5_3", "g:a_sjs1_2.13"]


@pytest.mark.parametrize(
    "module", ["g:a_2.13", "g:a_native0.5_3", "g:a_sjs1_2.13", "g:a_native0.5"]
)
def test_reject_expanded_seed_modules(module):
    d = document()
    d["projects"][0]["modules"] = [module]
    with pytest.raises(ValueError, match="cross-build suffix"):
        parse_config(d)


@pytest.mark.parametrize(
    "repo",
    ["zio/zio", "zio/zio-aws", "someone/zio-utils", "someone/my-zio-project", "com-lihaoyi/mill"],
)
def test_excluded_projects_cannot_reenter(repo):
    with pytest.raises(ValueError, match="excluded"):
        parse_config(document(repo))


def test_invalid_schema_and_project_limits():
    d = document()
    d["projects"] *= 761
    with pytest.raises(ValueError, match="760"):
        parse_config(d)
    d = document()
    d["projects"] *= 2
    with pytest.raises(ValueError, match="Duplicate repository"):
        parse_config(d)
    d = document()
    d["projects"][0]["artifacts"] = ["g:subject_2.13"]
    with pytest.raises(ValueError, match="Expanded artifact"):
        parse_config(d)
    with pytest.raises(ValueError, match="schema 2"):
        parse_config({"schema": 1})
    d = document()
    d["matrix"] = {"jvm": {"scala": [2.13, 3]}}
    with pytest.raises(ValueError, match="quoted strings"):
        parse_config(d)


def test_runtime_checks_published_coordinates_and_limits_seed_roots(tmp_path):
    urls = []

    def handler(request):
        urls.append(str(request.url))
        versions = [
            {"groupId": "g", "artifactId": name, "version": "2"}
            for name in ("subject_2.13", "subject_2.12", "subject_sjs1_3", "other_3")
        ]
        return httpx.Response(200, json=versions)

    config = parse_config(document())
    db = connect(tmp_path / "db.sqlite")
    collector = Collector(db, Fetcher(tmp_path / "evidence", httpx.MockTransport(handler)), config)
    assert collector.seed(config.projects[0]) == ["g:subject_2.13"]
    assert collector.roots() == ["g:subject_2.13@2"]
    assert {
        tuple(row) for row in db.execute("SELECT artifact,published FROM coordinate_checks")
    } == {("g:subject_2.13", 1), ("g:subject_3", 0)}
    assert len(urls) == 2


def test_missing_inventory_does_not_expand_guessed_coordinates(tmp_path):
    config = parse_config(document())
    db = connect(tmp_path / "db.sqlite")
    collector = Collector(
        db,
        Fetcher(tmp_path / "evidence", httpx.MockTransport(lambda r: httpx.Response(404))),
        config,
    )
    assert collector.seed(config.projects[0]) == []
    assert db.execute("SELECT count(*) FROM target_artifacts").fetchone()[0] == 0


def test_nonselected_target_module_does_not_count_as_fallout(tmp_path):
    db = fixture_db(tmp_path / "db.sqlite")
    db.execute("INSERT INTO metadata VALUES('seed_schema','2')")
    db.execute("INSERT INTO target_artifacts VALUES('g:b_3')")
    analyze(db)
    assert set(map(tuple, db.execute("SELECT * FROM fallout"))) == {("scala/b", "java/a")}
    assert validate(db)["fallout"] == 1


def test_selection_uses_main_sections_and_caps_projects():
    sections = main_sections(
        '<h2>Main A</h2><h3><a href="/awesome/a?sort=stars">a</a></h3><h3><a href="/awesome/b">b</a></h3><h2>Main B</h2><h3><a href="/awesome/c">c</a></h3>'
    )
    assert sections == {"Main A": ["a", "b"], "Main B": ["c"]}
    groups = {f"section-{i}": [f"child-{i}"] for i in range(14)}
    candidates: list[dict[str, JSON]] = [
        {
            "repository": f"owner/project-{i}-{rank}",
            "selection": [{"category": f"child-{i}", "rank": rank}],
        }
        for i in range(14)
        for rank in range(1, 15)
    ]
    candidates += [{"repository": "zio/zio", "selection": [{"category": "child-0", "rank": 0}]}]
    chosen = choose_projects(candidates, groups)
    assert len(chosen) == 140 and len({p["repository"] for p in chosen}) == 140
    selections = [p["selected_from"] for p in chosen]
    assert all(isinstance(c, list) for c in selections)
    selected_lists = [c for c in selections if isinstance(c, list)]
    assert len({str(c) for selected in selected_lists for c in selected}) == 14
    assert all(
        sum(f"child-{i}" in selected for selected in selected_lists) == 10 for i in range(14)
    )
    assert not any(excluded_repository(string(p["repository"])) for p in chosen)
    assert chosen == choose_projects(candidates, groups)


def test_committed_seeds_and_offline_plan(monkeypatch, capsys):
    from scala_security import cli
    from scala_security.cli import main

    path = Path(__file__).resolve().parents[1] / "config/seeds.yaml"
    raw = yaml.safe_load(path.read_text())
    config = parse_config(raw)
    assert 1 <= len(config.projects) <= 760
    assert config.matrix == DEFAULT_MATRIX
    assert not any(
        "artifacts" in p or excluded_repository(string(p["repository"])) for p in config.projects
    )
    assert "zio" not in yaml.safe_dump(raw["selection_policy"]).lower()
    assert "com-lihaoyi/mill" not in yaml.safe_dump(raw["selection_policy"])

    def forbidden(*args, **kwargs):
        raise AssertionError("Offline plan must not create an HTTP fetcher")

    monkeypatch.setattr(cli, "Fetcher", forbidden)
    monkeypatch.setattr("sys.argv", ["scala-security", "plan", "--seeds", str(path)])
    main()
    assert f'"projects": {len(config.projects)}' in capsys.readouterr().out


def test_offline_coordinates_remain_uncapped_for_metadata_ranking():
    d = document()
    d["projects"][0]["modules"] = [f"g:module{i:02}" for i in reversed(range(35))]
    config = parse_config(d)
    assert config.coordinates(config.projects[0]) == [
        f"g:module{i:02}_{binary}" for i in range(35) for binary in ("2.13", "3")
    ]


def test_closed_universe_excludes_external_consumers_and_intermediates(tmp_path):
    from scala_security.graph import paths

    db = fixture_db(tmp_path / "db.sqlite")
    db.execute("INSERT INTO metadata VALUES('seed_schema','2')")
    db.execute("INSERT INTO metadata VALUES('universe','seed')")
    db.executemany("INSERT INTO target_artifacts VALUES(?)", [("g:b_3",), ("g:c_3",)])
    analyze(db)
    assert set(map(tuple, db.execute("SELECT * FROM fallout"))) == {("scala/c", "scala/b")}
    assert validate(db)["fallout"] == 1
    # An excluded B coordinate cannot bridge a path from A to C.
    db.execute("UPDATE edges SET target='g:b_3@2' WHERE source='g:a@3'")
    assert "scala/c" in paths(db, ["g:a@3"])
    assert paths(db, ["g:a@3"], within={"g:a", "g:c_3"}) == {}


def test_forward_never_fetches_external_coordinates(tmp_path):
    db = connect(tmp_path / "db.sqlite")
    db.execute("INSERT INTO projects(id,seed) VALUES('scala/a',1)")
    db.execute("INSERT INTO artifacts(id,project) VALUES('g:a_2.13','scala/a')")
    db.execute("INSERT INTO versions VALUES('g:a_2.13@1','g:a_2.13','1',0)")
    requests = []

    def handler(request):
        requests.append(str(request.url))
        assert "external" not in str(request.url)
        if request.url.path.endswith(".pom"):
            return httpx.Response(200, text="<project/>")
        return httpx.Response(
            200,
            json={
                "dependencies": [
                    {
                        "package_name": "g:external",
                        "requirements": "1",
                        "kind": "compile",
                        "optional": False,
                    }
                ]
            },
        )

    collector = Collector(db, Fetcher(tmp_path / "evidence", httpx.MockTransport(handler)))
    collector.forward(["g:a_2.13@1"], {"g:a_2.13"})
    assert len(requests) == 2
    assert db.execute("SELECT count(*) FROM edges").fetchone()[0] == 0


def test_subsections_deduplicate_without_backfill():
    candidates: list[dict[str, JSON]] = [
        {
            "repository": f"scala/p{i}",
            "selection": [{"category": c, "rank": i + 1} for c in ("a", "b")],
        }
        for i in range(13)
    ]
    chosen = choose_projects(candidates, {"Main": ["a", "b"]})
    assert len(chosen) == 10
    assert all(p["selected_from"] == ["a", "b"] for p in chosen)
    assert [p["repository"] for p in chosen] == [f"scala/p{i}" for i in range(10)]


def test_reject_overfull_subsection():
    d = document()
    d["projects"] = [
        {"repository": f"scala/p{i}", "categories": ["a"], "modules": [f"g:p{i}"]}
        for i in range(11)
    ]
    with pytest.raises(ValueError, match="ten"):
        parse_config(d)


@pytest.mark.parametrize("missing_metadata", [False, True])
def test_artifact_selection_ranks_published_candidates_across_pages(tmp_path, missing_metadata):
    d = document()
    d["projects"][0]["modules"] = [f"g:m{i:02}" for i in range(25)]
    config = parse_config(d)
    requested = []

    def handler(request):
        requested.append(str(request.url))
        if request.url.path.endswith("/artifacts"):
            return httpx.Response(
                200, json=[{"groupId": "g", "artifactId": f"m{i:02}_2.13"} for i in range(24)]
            )
        assert request.url.path.endswith("/packages/lookup")
        if missing_metadata:
            return httpx.Response(404)
        page = int(request.url.params["page"])
        records = [
            {
                "name": f"g:m{i:02}_2.13",
                "dependent_packages_count": i,
                "registry": {"name": "repo1.maven.org"},
            }
            for i in range(23)
        ]
        # An excluded coordinate cannot win, even with the highest count.
        records.append(
            {
                "name": "g:m24_2.13",
                "dependent_packages_count": 9999,
                "registry": {"name": "repo1.maven.org"},
            }
        )
        return httpx.Response(
            200, json=records[:12] if page == 1 else records[12:] if page == 2 else []
        )

    db = connect(tmp_path / "db.sqlite")
    collector = Collector(db, Fetcher(tmp_path / "evidence", httpx.MockTransport(handler)), config)
    selected = collector.seed(config.projects[0])
    assert selected == (
        [f"g:m{i:02}_2.13" for i in range(20)]
        if missing_metadata
        else [f"g:m{i:02}_2.13" for i in range(22, 2, -1)]
    )
    assert db.execute("SELECT count(*) FROM target_artifacts").fetchone()[0] == 20
    assert db.execute("SELECT count(*) FROM artifact_selection").fetchone()[0] == 24
    assert (
        db.execute(
            "SELECT dependent_packages_count FROM artifact_selection WHERE artifact='g:m23_2.13'"
        ).fetchone()[0]
        is None
    )
    assert not any("dependent_packages?" in url or "/versions/" in url for url in requested)


def test_reject_old_artifact_cap():
    d = document()
    d["max_artifacts_per_project"] = 10
    with pytest.raises(ValueError, match="20 artifacts"):
        parse_config(d)


def test_five_hop_collection_and_sixth_hop_boundary(tmp_path):
    from scala_security.graph import paths

    db = connect(tmp_path / "db.sqlite")
    for i in range(7):
        db.execute("INSERT INTO projects(id,seed) VALUES(?,1)", (f"scala/p{i}",))
        db.execute("INSERT INTO artifacts(id,project) VALUES(?,?)", (f"g:p{i}_3", f"scala/p{i}"))
        db.execute("INSERT INTO versions VALUES(?,?,?,0)", (f"g:p{i}_3@1", f"g:p{i}_3", "1"))
    fetched = []

    def handler(request):
        if request.url.path.endswith(".pom"):
            return httpx.Response(200, text="<project/>")
        i = int(request.url.path.split("g:p")[1].split("_")[0])
        fetched.append(i)
        return httpx.Response(
            200,
            json={
                "dependencies": [
                    {
                        "package_name": f"g:p{i + 1}_3",
                        "requirements": "1",
                        "kind": "runtime",
                        "optional": False,
                    }
                ]
            },
        )

    Collector(db, Fetcher(tmp_path / "evidence", httpx.MockTransport(handler))).forward(
        ["g:p0_3@1"], {f"g:p{i}_3" for i in range(7)}
    )
    assert fetched == [0, 1, 2, 3, 4]
    found = paths(db, ["g:p0_3@1"])
    assert len(found["scala/p5"]) == 5
    assert "scala/p6" not in found
    db.execute(
        "INSERT INTO edges(source,target,scope,optional,exact) VALUES('g:p5_3@1','g:p6_3@1','runtime',0,1)"
    )
    assert "scala/p6" not in paths(db, ["g:p0_3@1"])
