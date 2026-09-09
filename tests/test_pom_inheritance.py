"""Effective inheritance, cross-checked with Maven 3.9.9 DefaultModelBuilder.

Maven replaces dependency/management/extension entries but merges plugin fields.
The unavailable-BOM policy regression is intentionally outside that comparison.
"""

from scala_security.configuration import DEFAULT_MATRIX
from scala_security.publication import memberships, pom_url, resolve_pom


def pom(name, body="", version="1", parent=""):
    group, artifact = name.split(":")
    parent_xml = (
        f"<parent><groupId>g</groupId><artifactId>{parent}</artifactId><version>1</version><relativePath/></parent>"
        if parent
        else ""
    )
    return f"<project><modelVersion>4.0.0</modelVersion>{parent_xml}<groupId>{group}</groupId><artifactId>{artifact}</artifactId><version>{version}</version>{body}</project>"


def dependency(version="", scope="", optional="", kind="", classifier=""):
    return (
        "<dependency><groupId>g</groupId><artifactId>lib</artifactId>"
        + "".join(
            f"<{tag}>{v}</{tag}>"
            for tag, v in [
                ("version", version),
                ("scope", scope),
                ("optional", optional),
                ("type", kind),
                ("classifier", classifier),
            ]
            if v
        )
        + "</dependency>"
    )


def dependencies(*deps):
    return "<dependencies>" + "".join(deps) + "</dependencies>"


def management(*deps):
    return "<dependencyManagement>" + dependencies(*deps) + "</dependencyManagement>"


def resolve(parent, child, grandparent="", extras=None):
    docs = {
        pom_url("g:parent", "1"): pom(
            "g:parent", parent, parent="grandparent" if grandparent else ""
        ),
        pom_url("g:child", "1"): pom("g:child", child, parent="parent"),
        pom_url("g:grandparent", "1"): pom("g:grandparent", grandparent),
    } | (extras or {})
    return resolve_pom("g:child", "1", lambda u: docs.get(u, ""))


def test_child_management_applies_to_inherited_unversioned_dependency():
    result = resolve(
        management(dependency("1")) + dependencies(dependency()), management(dependency("2"))
    )
    assert result.dependencies[0]["requirements"] == "2"
    assert not result.issues


def test_explicit_inherited_version_beats_child_management():
    result = resolve(dependencies(dependency("1")), management(dependency("2")))
    assert result.dependencies[0]["requirements"] == "1"


def test_local_management_replaces_matching_parent_entry():
    result = resolve(
        management(dependency("1", "test", "true")),
        management(dependency("2")) + dependencies(dependency()),
    )
    assert result.dependencies[0]["requirements"] == "2"
    assert result.dependencies[0]["kind"] == "compile"
    assert result.dependencies[0]["optional"] is False


def test_local_dependency_replaces_matching_parent_entry():
    result = resolve(
        dependencies(dependency("1", "compile", "true")), dependencies(dependency(scope="runtime"))
    )
    assert result.dependencies[0]["requirements"] == ""
    assert result.dependencies[0]["kind"] == "runtime"
    assert result.dependencies[0]["optional"] is False
    assert result.issues


def test_explicit_false_overrides_inherited_true_across_three_levels():
    result = resolve(
        management(dependency("2")),
        dependencies(dependency(optional="false")),
        management(dependency("1", "test", "true")) + dependencies(dependency()),
    )
    assert result.dependencies[0]["requirements"] == "2"
    assert result.dependencies[0]["kind"] == "compile"
    assert result.dependencies[0]["optional"] is False


def test_child_properties_reinterpolate_inherited_declarations():
    result = resolve(
        "<properties><lib.version>1</lib.version></properties>"
        + dependencies(dependency("${lib.version}")),
        "<properties><lib.version>2</lib.version></properties>",
    )
    assert result.dependencies[0]["requirements"] == "2"


def test_management_keeps_type_classifier_siblings_separate():
    result = resolve(
        management(
            dependency("1", "runtime"), dependency("4", "test", kind="test-jar", classifier="tests")
        ),
        management(dependency("2"))
        + dependencies(dependency(), dependency(kind="test-jar", classifier="tests")),
    )
    assert [(d["requirements"], d["kind"]) for d in result.dependencies] == [
        ("2", "compile"),
        ("4", "test"),
    ]


def test_child_managed_library_changes_unsuffixed_membership():
    lib = "<dependency><groupId>org.scala-lang</groupId><artifactId>scala-library</artifactId>{}</dependency>"
    result = resolve(
        management(lib.format("<version>2.13.18</version>")) + dependencies(lib.format("")),
        management(lib.format("<version>3.8.4</version>")),
    )
    assert memberships("g:child", "g:child", "1", result, DEFAULT_MATRIX) == {"jvm:_3"}


def test_parent_management_beats_import_and_first_import_wins():
    bom1 = management(dependency("3", "runtime"))
    bom2 = management(dependency("4", "test"))
    imports = management(
        *[
            f"<dependency><groupId>g</groupId><artifactId>bom{i}</artifactId><version>1</version><type>pom</type><scope>import</scope></dependency>"
            for i in (1, 2)
        ]
    )
    extras = {
        pom_url("g:bom1", "1"): pom("g:bom1", bom1),
        pom_url("g:bom2", "1"): pom("g:bom2", bom2),
    }
    assert (
        resolve("", imports + dependencies(dependency()), extras=extras).dependencies[0][
            "requirements"
        ]
        == "3"
    )
    assert (
        resolve(
            management(dependency("2")), imports + dependencies(dependency()), extras=extras
        ).dependencies[0]["requirements"]
        == "2"
    )


def test_missing_bom_policy_is_unchanged():
    missing = "<dependency><groupId>g</groupId><artifactId>missing</artifactId><version>1</version><type>pom</type><scope>import</scope></dependency>"
    result = resolve("", management(missing, dependency("1")) + dependencies(dependency()))
    assert result.issues
    assert result.dependencies[0]["kind"] == "compile"
    assert result.dependencies[0]["optional"] is False


def plugin(name="g:tool", version="", inherited=""):
    group, artifact = name.split(":")
    return (
        "<plugin>"
        + f"<groupId>{group}</groupId><artifactId>{artifact}</artifactId>"
        + (f"<version>{version}</version>" if version else "")
        + (f"<inherited>{inherited}</inherited>" if inherited else "")
        + "</plugin>"
    )


def build(active="", managed="", extensions=""):
    return (
        "<build><plugins>"
        + active
        + "</plugins><pluginManagement><plugins>"
        + managed
        + "</plugins></pluginManagement><extensions>"
        + extensions
        + "</extensions></build>"
    )


def test_active_parent_plugin_and_extension_are_inherited():
    ext = "<extension><groupId>g</groupId><artifactId>ext</artifactId><version>2</version></extension>"
    result = resolve(build(plugin(version="1"), extensions=ext), "")
    assert [(d["package_name"], d["requirements"], d["kind"]) for d in result.dependencies] == [
        ("g:tool", "1", "build"),
        ("g:ext", "2", "build"),
    ]
    assert not result.issues


def test_plugin_management_does_not_activate_plugins():
    result = resolve(build(managed=plugin(version="1")), "")
    assert not result.dependencies
    assert not result.issues


def test_plugin_version_from_management_and_child_override():
    parent = build(plugin(), plugin(version="1"))
    assert (
        resolve(parent, build(managed=plugin(version="2"))).dependencies[0]["requirements"] == "2"
    )
    assert resolve(parent, build(plugin(version="3"))).dependencies[0]["requirements"] == "3"


def test_noninherited_plugin_is_active_only_in_declaring_project():
    body = build(plugin(version="1", inherited="false"))
    assert not resolve(body, "").dependencies
    own = resolve_pom("g:parent", "1", lambda _: pom("g:parent", body))
    assert own.dependencies[0]["requirements"] == "1"
    assert resolve(body, build(plugin(version="2"))).dependencies[0]["requirements"] == "2"


def test_noninherited_management_does_not_supply_descendant_version():
    result = resolve(build(managed=plugin(version="1", inherited="false")), build(plugin()))
    assert result.dependencies[0]["requirements"] == ""
    assert result.issues


def test_plugin_inheritance_across_three_levels_and_explicit_false():
    assert resolve("", "", build(plugin(version="1"))).dependencies[0]["requirements"] == "1"
    assert not resolve(
        build(plugin(inherited="false")), "", build(plugin(version="1"))
    ).dependencies


def test_child_properties_apply_to_inherited_build_inputs():
    result = resolve(
        "<properties><tool.version>1</tool.version></properties>"
        + build(plugin(version="${tool.version}")),
        "<properties><tool.version>2</tool.version></properties>",
    )
    assert result.dependencies[0]["requirements"] == "2"


def test_excluded_unresolved_parent_plugin_does_not_leave_stale_warning():
    result = resolve(build(plugin(inherited="false")), "")
    assert not result.dependencies
    assert not result.issues


def test_profile_only_plugins_stay_inactive():
    result = resolve(
        "<profiles><profile><id>conditional</id>"
        + build(plugin(version="1"))
        + "</profile></profiles>",
        "",
    )
    assert not result.dependencies
    assert result.issues


def test_inherited_dependencies_and_plugins_reach_graph(tmp_path):
    import httpx

    from scala_security.analyze import analyze, validate
    from scala_security.collect import Collector
    from scala_security.configuration import parse_config
    from scala_security.data import connect
    from scala_security.http import Fetcher

    def owned(name, number, owner, body="", parent=""):
        return pom(name, body + f"<scm><url>https://github.com/{owner}</url></scm>", number, parent)

    names = {
        "seed/consumer": ("g:consumer_3", "2"),
        "seed/lib": ("g:lib_3", "2"),
        "seed/leaf": ("g:leaf_3", "1"),
        "seed/tool": ("g:tool_3", "7"),
    }
    config = parse_config(
        {
            "schema": 2,
            "matrix": DEFAULT_MATRIX,
            "projects": [
                {"repository": p, "categories": ["test"], "modules": [name.removesuffix("_3")]}
                for p, (name, _) in names.items()
            ],
        }
    )
    parent_body = (management(dependency("1")) + dependencies(dependency())).replace(
        "lib</artifactId>", "lib_3</artifactId>"
    ) + build(plugin("g:tool_3", "7"))
    child_body = management(dependency("2")).replace("lib</artifactId>", "lib_3</artifactId>")
    docs = {pom_url(name, v): owned(name, v, p) for p, (name, v) in names.items()}
    docs[pom_url("g:parent", "1")] = pom("g:parent", parent_body)
    docs[pom_url("g:consumer_3", "2")] = owned(
        "g:consumer_3", "2", "seed/consumer", child_body, "parent"
    )
    docs[pom_url("g:lib_3", "2")] = owned(
        "g:lib_3",
        "2",
        "seed/lib",
        dependencies(dependency("1")).replace("lib</artifactId>", "leaf_3</artifactId>"),
    )
    docs[pom_url("g:lib_3", "1")] = owned("g:lib_3", "1", "seed/lib")

    def handler(request):
        url = str(request.url)
        if url in docs:
            return httpx.Response(200, text=docs[url])
        for project, (name, version) in names.items():
            if "/projects/" + project + "/" in url:
                group, artifact = name.split(":")
                return httpx.Response(
                    200, json=[{"groupId": group, "artifactId": artifact, "version": version}]
                )
        return httpx.Response(404)

    db = connect(tmp_path / "snapshot.sqlite")
    Collector(db, Fetcher(tmp_path / "evidence", httpx.MockTransport(handler)), config).run(
        config.projects
    )
    analyze(db)
    validate(db)
    targets = {
        r[0] for r in db.execute("SELECT target FROM fallout WHERE dependant='seed/consumer'")
    }
    assert targets == {"seed/lib", "seed/leaf", "seed/tool"}
    assert (
        db.execute(
            "SELECT 1 FROM edges WHERE source='g:consumer_3@2' AND target='g:lib_3@1'"
        ).fetchone()
        is None
    )
    assert (
        db.execute(
            "SELECT scope FROM edges WHERE source='g:consumer_3@2' AND target='g:tool_3@7'"
        ).fetchone()[0]
        == "build"
    )


def test_redeclaring_noninherited_parent_plugin_requires_own_version():
    result = resolve(build(plugin(version="1", inherited="false")), build(plugin()))
    assert result.dependencies[0]["requirements"] == ""
    assert result.issues


def test_noninherited_management_with_active_parent_plugin():
    result = resolve(build(plugin(), plugin(version="1", inherited="false")), "")
    assert result.dependencies[0]["requirements"] == ""
    assert result.issues


def test_child_extension_replaces_parent_extension():
    parent = "<extension><groupId>g</groupId><artifactId>ext</artifactId><version>1</version></extension>"
    child = "<extension><groupId>g</groupId><artifactId>ext</artifactId></extension>"
    result = resolve(build(extensions=parent), build(extensions=child))
    assert result.dependencies[0]["requirements"] == ""
    assert result.issues
