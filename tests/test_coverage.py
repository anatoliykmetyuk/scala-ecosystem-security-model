"""Missing evidence is not a zero incoming exposure value."""

import json

from scala_security.coverage import project_coverage
from scala_security.data import connect


def test_coverage_states_and_counts(tmp_path):
    db = connect(tmp_path / "snapshot.sqlite")
    db.execute("INSERT INTO projects(id,seed) VALUES('g/p',1)")
    c = project_coverage(db, "g/p")
    assert c["status"] == "unavailable" and "Project latest release unavailable" in c["reasons"]
    db.execute("UPDATE projects SET latest='1'")
    assert "No selected matching release coordinates" in project_coverage(db, "g/p")["reasons"]
    for artifact in ("g:a", "g:b"):
        db.execute("INSERT INTO artifacts(id,project) VALUES(?,'g/p')", (artifact,))
        db.execute("INSERT INTO target_artifacts VALUES(?)", (artifact,))
        db.execute("INSERT INTO versions VALUES(?,?,'1',0)", (artifact + "@1", artifact))
    assert project_coverage(db, "g/p")["status"] == "unavailable"
    db.execute("UPDATE versions SET fetched=1 WHERE artifact='g:a'")
    db.execute("INSERT INTO version_coverage VALUES('g:a@1',1,1,'[]')")
    c = project_coverage(db, "g/p")
    assert c["status"] == "partial" and c["usable"] == 1 and c["roots"] == 2
    db.execute("UPDATE versions SET fetched=1")
    db.execute(
        "INSERT INTO version_coverage VALUES('g:b@1',0,0,?)",
        (json.dumps(["Unresolved dependency versions"]),),
    )
    assert project_coverage(db, "g/p")["status"] == "partial"
    db.execute("UPDATE version_coverage SET usable=1,complete=1,reasons='[]'")
    # Successfully resolved empty dependency lists are usable zero-path evidence.
    assert project_coverage(db, "g/p")["status"] == "complete"
    assert not project_coverage(db, "g/p")["reasons"]


def test_historical_fetch_is_not_assumed_complete(tmp_path):
    db = connect(tmp_path / "snapshot.sqlite")
    db.execute("INSERT INTO projects(id,seed,latest) VALUES('g/p',1,'1')")
    db.execute("INSERT INTO artifacts(id,project) VALUES('g:a','g/p')")
    db.execute("INSERT INTO target_artifacts VALUES('g:a')")
    db.execute("INSERT INTO versions VALUES('g:a@1','g:a','1',1)")
    assert project_coverage(db, "g/p")["status"] == "unavailable"
    assert (
        "Historical snapshot lacks declaration-resolution coverage"
        in project_coverage(db, "g/p")["reasons"]
    )
