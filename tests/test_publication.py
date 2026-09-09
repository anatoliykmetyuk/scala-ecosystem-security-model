"""Publication, cell allocation, and historical-version regression fixtures."""

import json
import random

import httpx
import pytest

from scala_security.analyze import analyze, validate
from scala_security.collect import Collector
from scala_security.configuration import DEFAULT_MATRIX, expand, modules_for, parse_config
from scala_security.data import JSON, connect
from scala_security.http import Fetcher
from scala_security.publication import memberships, pom_url, resolve_pom
from scala_security.selection import rank_artifacts

SBT: dict[str, JSON] = {
    "sbt": {"variants": [{"scala": "2.12", "sbt": "1.0"}, {"scala": "3", "sbt": "2"}]}
}


def pom(name, version="1", body=""):
    group, artifact = name.split(":")
    return f"<project><groupId>{group}</groupId><artifactId>{artifact}</artifactId><version>{version}</version>{body}</project>"


def dep(name, version):
    group, artifact = name.split(":")
    return f"<dependency><groupId>{group}</groupId><artifactId>{artifact}</artifactId><version>{version}</version></dependency>"


def test_balancing_popularity_and_overlapping_cells():
    candidates = {f"play:module{i}_{b}": {b} for i in range(60) for b in ("2.13", "3")}
    counts = dict.fromkeys(candidates, 0)
    selected = rank_artifacts(candidates, counts, 50)[:50]
    assert sum(a.endswith("_3") for a in selected) == 25
    shuffled = list(candidates.items())
    random.Random(17).shuffle(shuffled)
    assert rank_artifacts(dict(shuffled), counts, 50)[:50] == selected
    # Strictly higher counts win. Known zero precedes unknown.
    counts = {"high": 10, "zero": 0}
    assert rank_artifacts({"unknown": {"a"}, "zero": {"a"}, "high": {"b"}}, counts, 2)[:2] == [
        "high",
        "zero",
    ]
    uneven = {"single": {"a"}, **{str(i): {"b"} for i in range(10)}}
    assert "single" in rank_artifacts(uneven, {}, 5)[:5]
    for cap in (1, 2, 3, 10):
        overlapping = {"both": {"a", "b"}, **uneven}
        selected = rank_artifacts(overlapping, {}, cap)[:cap]
        assert len(set(selected)) == cap
    cells = {str(i): {str(i)} for i in range(10)}
    assert rank_artifacts(cells, {}, 3)[:3] != ["0", "1", "2"]


@pytest.mark.parametrize(
    "libraries,expected",
    [
        ([("org.scala-lang:scala-library", "2.13.18")], {"jvm:_2.13"}),
        ([("org.scala-lang:scala3-library_3", "3.3.7")], {"jvm:_3"}),
        (
            [
                ("org.scala-lang:scala-library", "2.13.18"),
                ("org.scala-lang:scala3-library_3", "3.3.7"),
            ],
            {"jvm:_2.13", "jvm:_3"},
        ),
        ([], set()),
        ([("org.scala-lang:scala-library", "${unresolved}")], set()),
    ],
)
def test_direct_unsuffixed_filters(libraries, expected):
    xml = pom(
        "g:plain", body="<dependencies>" + "".join(dep(*x) for x in libraries) + "</dependencies>"
    )
    pub = resolve_pom("g:plain", "1", lambda _: xml)
    assert memberships("g:plain", "g:plain", "1", pub, DEFAULT_MATRIX) == expected
    assert (
        memberships(
            "g:plain", "g:plain", "1", pub, {"scala_js": {"versions": ["1"], "scala": ["3"]}}
        )
        == set()
    )
    assert memberships("g:plain", "g:plain", "1", pub, {"jvm": {"scala": ["2.12"]}}) == set()


def test_library_self_classification_and_nonexistent_identity():
    for name, version, cell in [
        ("org.scala-lang:scala-library", "2.13.18", "jvm:_2.13"),
        ("org.scala-lang:scala3-library_3", "3.8.4", "jvm:_3"),
    ]:
        pub = resolve_pom(name, version, lambda _: pom(name, version))
        assert memberships(name, name, version, pub, DEFAULT_MATRIX) == {cell}
    assert not resolve_pom("g:a", "2", lambda _: pom("g:a", "1")).verified
    assert not resolve_pom("g:a", "2", lambda _: "").verified


def test_parent_management_and_bom_resolve_only_immediate_dependencies():
    library = "org.scala-lang:scala-library"
    parent = pom(
        "g:parent",
        body="<properties><scala.line>2.13.18</scala.line></properties><dependencyManagement><dependencies>"
        + dep(library, "${scala.line}")
        + "</dependencies></dependencyManagement>",
    )
    child = "<project><parent><groupId>g</groupId><artifactId>parent</artifactId><version>1</version></parent><artifactId>child</artifactId><dependencies><dependency><groupId>org.scala-lang</groupId><artifactId>scala-library</artifactId></dependency></dependencies></project>"
    documents = {pom_url("g:parent", "1"): parent, pom_url("g:child", "1"): child}
    pub = resolve_pom("g:child", "1", lambda u: documents.get(u, ""))
    assert not pub.issues
    assert memberships("g:child", "g:child", "1", pub, DEFAULT_MATRIX) == {"jvm:_2.13"}
    bom = pom(
        "g:bom",
        body="<dependencyManagement><dependencies>"
        + dep(library, "2.13.18")
        + "</dependencies></dependencyManagement>",
    )
    body = (
        "<dependencyManagement><dependencies>"
        + dep("g:bom", "1").replace(
            "</dependency>", "<type>pom</type><scope>import</scope></dependency>"
        )
        + "</dependencies></dependencyManagement>"
    )
    documents[pom_url("g:bom", "1")] = bom
    documents[pom_url("g:child", "1")] = pom(
        "g:child",
        body=body
        + "<dependencies><dependency><groupId>org.scala-lang</groupId><artifactId>scala-library</artifactId></dependency></dependencies>",
    )
    assert memberships(
        "g:child",
        "g:child",
        "1",
        resolve_pom("g:child", "1", lambda u: documents.get(u, "")),
        DEFAULT_MATRIX,
    ) == {"jvm:_2.13"}
    # A managed library with no dependency declaration is not membership evidence.
    documents[pom_url("g:child", "1")] = pom("g:child", body=body)
    assert not memberships(
        "g:child",
        "g:child",
        "1",
        resolve_pom("g:child", "1", lambda u: documents.get(u, "")),
        DEFAULT_MATRIX,
    )


def test_sbt_suffixes_legacy_and_disabled_cells():
    matrix = DEFAULT_MATRIX | SBT
    assert expand(["g:plugin"], SBT) == ["g:plugin_2.12_1.0", "g:plugin_sbt2_3"]
    assert modules_for(
        ["g:plugin_2.12_1.0", "g:plugin_sbt2_3", "g:plugin_sbt2.0.0-M4_3"], matrix
    ) == ["g:plugin"]
    for name, cell in [("g:plugin_2.12_1.0", "sbt:_2.12_1.0"), ("g:plugin_sbt2_3", "sbt:_sbt2_3")]:
        pub = resolve_pom(name, "1", lambda _: pom(name))
        assert memberships(name, "g:plugin", "1", pub, matrix) == {cell}
        assert not memberships(name, "g:plugin", "1", pub, DEFAULT_MATRIX)
    for scala, sbt, cell in [
        ("2.12.20", "1.10.7", "sbt:_2.12_1.0"),
        ("3.7.3", "2.1.0", "sbt:_sbt2_3"),
    ]:
        pub = resolve_pom(
            "g:plugin",
            "1",
            lambda _: pom(
                "g:plugin",
                body=f"<properties><scalaVersion>{scala}</scalaVersion><sbtVersion>{sbt}</sbtVersion></properties>",
            ),
        )
        assert memberships("g:plugin", "g:plugin", "1", pub, matrix) == {cell}
        assert not memberships("g:plugin", "g:plugin", "1", pub, DEFAULT_MATRIX)
    for properties in (
        "<sbtVersion>1.0</sbtVersion>",
        "<sbtVersion>2.0.0-M4</sbtVersion><scalaVersion>3</scalaVersion>",
    ):
        pub = resolve_pom(
            "g:plugin",
            "1",
            lambda _: pom("g:plugin", body="<properties>" + properties + "</properties>"),
        )
        assert not memberships("g:plugin", "g:plugin", "1", pub, matrix)
    with pytest.raises(ValueError):
        expand(["g:a"], {"sbt": {"variants": [{"scala": "2.13", "sbt": "1.0"}]}})


def test_end_to_end_unsuffixed_scala_gatling_and_sbt(tmp_path):
    releases = {
        "scala/scala": ("org.scala-lang:scala-library", "2.13.18"),
        "twitter/finagle": ("com.twitter:finagle-core_2.13", "24.2.0"),
        "gatling/gatling": ("io.gatling:gatling-core", "3.15.1"),
        "sbt/sbt-web": ("com.github.sbt:sbt-web_2.12_1.0", "1.5.8"),
        "sbt/sbt-protoc": ("com.thesamet:sbt-protoc_sbt2_3", "1.0.7"),
    }
    modules = [
        "org.scala-lang:scala-library",
        "com.twitter:finagle-core",
        "io.gatling:gatling-core",
        "com.github.sbt:sbt-web",
        "com.thesamet:sbt-protoc",
    ]
    config = parse_config(
        {
            "schema": 2,
            "matrix": DEFAULT_MATRIX | SBT,
            "projects": [
                {"repository": p, "categories": ["test"], "modules": [m]}
                for p, m in zip(releases, modules)
            ],
        }
    )
    documents = {
        pom_url(name, version): pom(
            name,
            version,
            ("<dependencies>" + dep("org.scala-lang:scala-library", "2.13.6") + "</dependencies>")
            if p in ("twitter/finagle", "gatling/gatling")
            else "",
        )
        for p, (name, version) in releases.items()
    }
    documents[pom_url("org.scala-lang:scala-library", "2.13.6")] = pom(
        "org.scala-lang:scala-library", "2.13.6"
    )

    for owner, (name, _) in releases.items():
        for url in list(documents):
            if name.split(":")[1] + "/" in url:
                documents[url] = documents[url].replace(
                    "</project>", f"<scm><url>https://github.com/{owner}</url></scm></project>"
                )

    def handler(request):
        url = str(request.url)
        assert not url.endswith(".jar")
        if url.endswith(".pom"):
            return (
                httpx.Response(200, text=documents[url])
                if url in documents
                else httpx.Response(404)
            )
        for project, (name, version) in releases.items():
            if "/projects/" + project + "/" in url:
                group, artifact = name.split(":")
                # Incorrect suffixed index records for the two unsuffixed artifacts.
                if project in ("scala/scala", "gatling/gatling"):
                    artifact += "_2.13"
                return httpx.Response(
                    200, json=[{"groupId": group, "artifactId": artifact, "version": version}]
                )
        return httpx.Response(404)

    db = connect(tmp_path / "db.sqlite")
    collector = Collector(db, Fetcher(tmp_path / "evidence", httpx.MockTransport(handler)), config)
    collector.run(config.projects)
    analyze(db)
    assert validate(db)["fallout"] == 2
    assert db.execute(
        "SELECT 1 FROM fallout WHERE target='scala/scala' AND dependant='twitter/finagle'"
    ).fetchone()
    assert db.execute(
        "SELECT 1 FROM fallout WHERE target='scala/scala' AND dependant='gatling/gatling'"
    ).fetchone()
    assert db.execute("SELECT count(*) FROM target_artifacts").fetchone()[0] == 7
    assert db.execute(
        "SELECT 1 FROM edges WHERE target='org.scala-lang:scala-library@2.13.6'"
    ).fetchone()
    pub = db.execute(
        "SELECT dependencies,issues FROM publications WHERE artifact='io.gatling:gatling-core'"
    ).fetchone()
    assert json.loads(pub[0]) and "Scaladex" in pub[1]


def test_recorded_maven_publications():
    from pathlib import Path

    folder = Path(__file__).parent / "fixtures" / "publications"
    sources = json.loads((folder / "sources.json").read_text())
    for file, record in sources.items():
        pub = resolve_pom(
            record["coordinate"],
            record["version"],
            lambda url: (folder / file).read_text() if url == record["source"] else "",
        )
        assert pub.verified
        module = record["coordinate"].replace("_2.12_1.0", "").replace("_sbt2_3", "")
        cells = memberships(
            record["coordinate"], module, record["version"], pub, DEFAULT_MATRIX | SBT
        )
        assert cells
        if "gatling" in file:
            assert cells == {"jvm:_2.13"}
        if "sbt-web" in file:
            assert cells == {"sbt:_2.12_1.0"}
        if "sbt-protoc" in file:
            assert cells == {"sbt:_sbt2_3"}


def test_parent_property_override_and_unresolved_management():
    parent = pom(
        "g:parent",
        body="<properties><scala.line>2.12.20</scala.line></properties><dependencyManagement><dependencies>"
        + dep("org.scala-lang:scala-library", "${scala.line}")
        + "</dependencies></dependencyManagement>",
    )
    child = "<project><parent><groupId>g</groupId><artifactId>parent</artifactId><version>1</version></parent><artifactId>child</artifactId><properties><scala.line>2.13.18</scala.line></properties><dependencies><dependency><groupId>org.scala-lang</groupId><artifactId>scala-library</artifactId></dependency></dependencies></project>"
    documents = {pom_url("g:parent", "1"): parent, pom_url("g:child", "1"): child}
    pub = resolve_pom("g:child", "1", lambda url: documents.get(url, ""))
    assert memberships("g:child", "g:child", "1", pub, DEFAULT_MATRIX) == {"jvm:_2.13"}
    documents.pop(pom_url("g:parent", "1"))
    pub = resolve_pom("g:child", "1", lambda url: documents.get(url, ""))
    assert pub.verified and pub.issues
    assert not memberships("g:child", "g:child", "1", pub, DEFAULT_MATRIX)
    assert pub.dependencies[0]["kind"] == "unknown"
    assert pub.dependencies[0]["optional"] is None


def test_same_module_distinct_publications_and_overlapping_filters(tmp_path):
    config = parse_config(
        {
            "schema": 2,
            "matrix": DEFAULT_MATRIX,
            "projects": [{"repository": "g/a", "categories": ["test"], "modules": ["g:a"]}],
        }
    )
    body = (
        "<dependencies>"
        + dep("org.scala-lang:scala-library", "2.13.18")
        + dep("org.scala-lang:scala3-library_3", "3.3.7")
        + "</dependencies>"
    )

    def handler(request):
        if request.url.path.endswith(".pom"):
            name = request.url.path.split("/")[-3]
            if name in ["a", "a_3"]:
                return httpx.Response(200, text=pom("g:" + name, body=body))
            return httpx.Response(404)
        return httpx.Response(200, json=[{"groupId": "g", "artifactId": "a_3", "version": "1"}])

    db = connect(tmp_path / "db.sqlite")
    c = Collector(db, Fetcher(tmp_path / "evidence", httpx.MockTransport(handler)), config)
    assert set(c.seed(config.projects[0])) == {"g:a", "g:a_3"}
    cells = json.loads(
        db.execute("SELECT cells FROM publications WHERE artifact='g:a'").fetchone()[0]
    )
    assert cells == ["jvm:_2.13", "jvm:_3"]
    assert db.execute("SELECT count(*) FROM target_artifacts").fetchone()[0] == 2


def test_readme_matrix_example_is_parseable():
    import re
    from pathlib import Path

    import yaml

    readme = (Path(__file__).parents[1] / "README.md").read_text()
    match = re.search(r"```yaml\n(.*?)\n```", readme, re.S)
    assert match is not None
    example = match.group(1)
    config = parse_config(yaml.safe_load(example))
    assert len(config.coordinates(config.projects[0])) == 4


def test_unusable_scope_and_api_fallback_evidence(tmp_path):
    def handler(request):
        if request.url.path.endswith(".pom"):
            return httpx.Response(404)
        return httpx.Response(
            200,
            json={
                "dependencies": [
                    {
                        "package_name": "g:b",
                        "requirements": "1",
                        "kind": "unknown",
                        "optional": False,
                    }
                ]
            },
        )

    c = Collector(
        connect(tmp_path / "db.sqlite"),
        Fetcher(tmp_path / "evidence", httpx.MockTransport(handler)),
    )
    _, deps, source, fetched, usable, issues, ownership = c.version("g:a@1")
    assert fetched and not usable and issues and deps
    assert "/versions/1" in source and not source.endswith(".pom")


def test_all_platform_cells_coexist_without_sbt_leaking_into_jvm():
    matrix = (
        DEFAULT_MATRIX
        | SBT
        | {
            "scala_js": {"versions": ["1"], "scala": ["3"]},
            "scala_native": {"versions": ["0.5"], "scala": ["3"]},
        }
    )
    names = expand(["g:a"], matrix)
    assert len(names) == 6 and "g:a_2.12" not in names
    for name in names:
        pub = resolve_pom(name, "1", lambda _: pom(name))
        cells = memberships(name, "g:a", "1", pub, matrix)
        assert len(cells) == 1
        assert modules_for([name], matrix) == ["g:a"]
