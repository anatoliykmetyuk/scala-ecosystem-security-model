"""Policy regressions: historical targets, exact ownership and POM identity."""

import httpx
import pytest

from scala_security.analyze import analyze, validate
from scala_security.collect import Collector
from scala_security.configuration import DEFAULT_MATRIX, parse_config
from scala_security.data import connect
from scala_security.http import Fetcher
from scala_security.publication import pom_url, resolve_pom


def pom(name, version, owner="", body=""):
    group, artifact = name.split(":")
    scm = f"<scm><url>https://github.com/{owner}</url></scm>" if owner else ""
    return f"<project><groupId>{group}</groupId><artifactId>{artifact}</artifactId><version>{version}</version>{scm}{body}</project>"


def dep(name, version, extra=""):
    group, artifact = name.split(":")
    return f"<dependency><groupId>{group}</groupId><artifactId>{artifact}</artifactId><version>{version}</version>{extra}</dependency>"


def test_management_warnings_and_classifier_siblings():
    parent = pom(
        "g:parent",
        "1",
        body="<profiles><profile><id>optional</id></profile></profiles><build><plugins><plugin><artifactId>unversioned</artifactId></plugin></plugins></build>",
    )
    child = pom(
        "g:child",
        "1",
        body="<parent><groupId>g</groupId><artifactId>parent</artifactId><version>1</version></parent><dependencies>"
        + dep("g:target", "1")
        + dep(
            "g:target",
            "1",
            "<type>test-jar</type><classifier>tests</classifier><scope>test</scope>",
        )
        + "</dependencies>",
    )
    docs = {pom_url("g:parent", "1"): parent, pom_url("g:child", "1"): child}
    result = resolve_pom("g:child", "1", lambda u: docs.get(u, ""))
    assert result.issues  # Coverage stays partial, but ordinary defaults remain known.
    assert [(d["kind"], d["optional"]) for d in result.dependencies] == [
        ("compile", False),
        ("test", False),
        ("build", False),
    ]
    missing = resolve_pom("g:child", "1", lambda u: child if u.endswith("child-1.pom") else "")
    assert missing.dependencies[0]["kind"] == "unknown"
    assert missing.dependencies[0]["optional"] is None


def test_management_type_and_classifier_are_independent():
    body = (
        "<dependencyManagement><dependencies>"
        + dep("g:target", "1", "<scope>runtime</scope>")
        + dep(
            "g:target",
            "2",
            "<type>test-jar</type><classifier>tests</classifier><scope>test</scope>",
        )
        + "</dependencies></dependencyManagement><dependencies><dependency><groupId>g</groupId><artifactId>target</artifactId></dependency></dependencies>"
    )
    result = resolve_pom("g:root", "1", lambda _: pom("g:root", "1", body=body))
    assert result.dependencies[0]["requirements"] == "1"
    assert result.dependencies[0]["kind"] == "runtime"


@pytest.mark.parametrize("target_latest", ["9", ""])
@pytest.mark.parametrize("target_coordinate", ["g:b_3", "g:b"])
def test_historical_target_and_version_owner_pipeline(tmp_path, target_latest, target_coordinate):
    releases = {
        "seed/a": "2",
        "seed/b": target_latest,
        "scala/scala": "2.13.18",
        "scala/scala3": "3.8.4",
    }
    modules = {
        "seed/a": "g:a",
        "seed/b": "g:b",
        "scala/scala": "org.scala-lang:scala-library",
        "scala/scala3": "org.scala-lang:scala3-library",
    }
    inventory = {
        "seed/a": "g:a_3",
        "seed/b": target_coordinate,
        "scala/scala": "org.scala-lang:scala-library",
        "scala/scala3": "org.scala-lang:scala3-library_3",
    }
    docs = {
        pom_url("g:a_3", "2"): pom(
            "g:a_3",
            "2",
            "seed/a",
            "<dependencies>"
            + dep(target_coordinate, "1")
            + dep("org.scala-lang:scala-library", "3.8.4")
            + "</dependencies>",
        ),
        pom_url(target_coordinate, "1"): pom(
            target_coordinate,
            "1",
            "seed/b",
            "<dependencies>" + dep("org.scala-lang:scala-library", "2.13.18") + "</dependencies>",
        ),
        pom_url("org.scala-lang:scala-library", "2.13.18"): pom(
            "org.scala-lang:scala-library", "2.13.18", "scala/scala"
        ),
        pom_url("org.scala-lang:scala-library", "3.8.4"): pom(
            "org.scala-lang:scala-library", "3.8.4", "scala/scala3"
        ),
        pom_url("org.scala-lang:scala3-library_3", "3.8.4"): pom(
            "org.scala-lang:scala3-library_3", "3.8.4", "scala/scala3"
        ),
    }
    config = parse_config(
        {
            "schema": 2,
            "matrix": DEFAULT_MATRIX,
            "projects": [
                {"repository": p, "categories": ["test"], "modules": [modules[p]]} for p in releases
            ],
        }
    )

    def handler(request):
        url = str(request.url)
        if url in docs:
            return httpx.Response(200, text=docs[url])
        if request.url.path.endswith("/packages/g:b"):
            return httpx.Response(
                200,
                json={"latest_release_number": "1", "repository_url": "https://github.com/seed/b"},
            )
        for project, number in releases.items():
            if "/projects/" + project + "/" in url:
                group, artifact = inventory[project].split(":")
                return httpx.Response(
                    200, json=[{"groupId": group, "artifactId": artifact, "version": number}]
                )
        return httpx.Response(404)

    db = connect(tmp_path / "snapshot.sqlite")
    Collector(db, Fetcher(tmp_path / "cache", httpx.MockTransport(handler)), config).run(
        config.projects
    )
    analyze(db)
    validate(db)
    from scala_security.coverage import project_coverage

    assert project_coverage(db, "scala/scala3")["roots"] == 2
    pairs = set(map(tuple, db.execute("SELECT * FROM fallout")))
    assert ("seed/b", "seed/a") in pairs  # B@9 does not exist, B@1 remains eligible.
    assert ("scala/scala3", "seed/a") in pairs
    assert ("scala/scala", "seed/a") in pairs  # Independent B@1 -> Scala 2 path.
    assert not any(dependant == "seed/b" for _, dependant in pairs)  # No older consumer fallback.
    assert (
        db.execute(
            "SELECT project FROM version_ownership WHERE version='org.scala-lang:scala-library@3.8.4'"
        ).fetchone()[0]
        == "scala/scala3"
    )
    assert (
        db.execute(
            "SELECT project FROM version_ownership WHERE version='org.scala-lang:scala-library@2.13.18'"
        ).fetchone()[0]
        == "scala/scala"
    )


def test_owner_redirect_conflict_and_outside_seed(tmp_path):
    config = parse_config(
        {
            "schema": 2,
            "matrix": DEFAULT_MATRIX,
            "projects": [{"repository": "new/repo", "categories": ["test"], "modules": ["g:a"]}],
        }
    )

    def handler(request):
        if request.url.path == "/repos/old/repo":
            return httpx.Response(200, json={"full_name": "new/repo"})
        return httpx.Response(404)

    c = Collector(
        connect(tmp_path / "db"), Fetcher(tmp_path / "cache", httpx.MockTransport(handler)), config
    )
    pub = resolve_pom("g:a", "1", lambda _: pom("g:a", "1", "old/repo"))
    assert c.publication_owner("g:a", pub)[0] == "new/repo"
    pub.repositories = {"outside/wrapper"}
    assert c.publication_owner("g:a", pub)[0] == "outside/wrapper"
    pub.repositories = {"new/repo", "outside/wrapper"}
    assert c.publication_owner("g:a", pub)[:2] == ("", "conflict")


def test_outside_owner_cannot_bridge_selected_coordinate(tmp_path):
    db = connect(tmp_path / "snapshot.sqlite")
    db.executemany(
        "INSERT INTO metadata VALUES(?,?)",
        [
            ("ownership_policy", "publication-v1"),
            ("seed_schema", "2"),
            ("universe", "seed"),
            ("collected_at", "2026-09-09T00:00:00+00:00"),
        ],
    )
    for name in ("a", "b", "c"):
        db.execute("INSERT INTO projects(id,seed,latest) VALUES(?,1,?)", ("seed/" + name, "1"))
        db.execute("INSERT INTO artifacts(id,project) VALUES(?,?)", ("g:" + name, "seed/" + name))
        db.execute("INSERT INTO target_artifacts VALUES(?)", ("g:" + name,))
        db.execute("INSERT INTO versions VALUES(?,?,?,1)", ("g:" + name + "@1", "g:" + name, "1"))
        db.execute(
            "INSERT INTO version_ownership VALUES(?,?,?,?)",
            (
                "g:" + name + "@1",
                "outside/wrapper" if name == "b" else "seed/" + name,
                "resolved",
                "[]",
            ),
        )
    for start, end in [("a", "b"), ("b", "c")]:
        db.execute(
            "INSERT INTO edges(source,target,scope,optional,exact) VALUES(?,?,?,0,1)",
            ("g:" + start + "@1", "g:" + end + "@1", "compile"),
        )
    analyze(db)
    assert validate(db)["fallout"] == 0


def test_scm_git_suffix_before_tree_path_is_same_repository():
    xml = pom("g:a", "1").replace(
        "</project>",
        "<scm><url>https://github.com/owner/repo/tree/main</url><connection>scm:git:git://github.com/owner/repo.git.git/tree/main</connection></scm></project>",
    )
    assert resolve_pom("g:a", "1", lambda _: xml).repositories == {"owner/repo"}
