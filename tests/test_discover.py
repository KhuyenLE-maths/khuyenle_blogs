from __future__ import annotations

import json
import sqlite3
from datetime import timedelta

import pytest

from conftest import NOW, no_sleep, run_discover
from msx import db
from msx.hf import CLAIM_FIELDS, HubError, with_retry
from msx.project import iso

LM = "fixturelab/fixture-lm-8b"
VL = "fixturevision/fixture-vl-3b"


def claim_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]


def test_discover_selects_filters_and_reports(project, conn, client):
    summary = run_discover(project, conn, client)

    assert sorted(row["id"] for row in db.list_models(conn)) == [LM, VL]
    assert summary["skipped"] == 1  # the -GGUF repo
    assert summary["authors_with_no_models"] == ["FixtureEmpty"]
    assert summary["errors"] == []
    run = db.recent_runs(conn, 1)[0]
    assert run["ok"] == 1 and json.loads(run["message"])["checked"] == 2


def test_discover_is_idempotent(project, conn, client):
    first = run_discover(project, conn, client)
    count = claim_count(conn)
    second = run_discover(project, conn, client)

    assert first["new_claims"] == 2 * len(CLAIM_FIELDS) == count
    assert second["new_claims"] == 0
    assert second["new_models"] == 0
    assert claim_count(conn) == count


def test_changed_license_adds_a_row_and_keeps_the_first(project, conn, client, fixture_dir):
    run_discover(project, conn, client)
    path = fixture_dir / "models" / "FixtureLab__Fixture-LM-8B.json"
    data = json.loads(path.read_text())
    data["cardData"]["license"] = "mit"
    path.write_text(json.dumps(data))

    summary = run_discover(project, conn, client, now=NOW + timedelta(days=1))

    assert summary["new_claims"] == 1
    history = db.claim_history(conn, LM, "license")
    assert [json.loads(row["value"]) for row in history] == ["apache-2.0", "mit"]
    changes = db.material_changes_since(conn, LM, iso(NOW))
    assert [(c["field"], c["old"], c["new"]) for c in changes] == [("license", "apache-2.0", "mit")]


def test_missing_parameter_count_is_unknown_never_a_number(project, conn, client):
    run_discover(project, conn, client)

    vl = db.current_claims(conn, VL)["parameters"]
    assert vl["status"] == "unknown"
    assert vl["value"] is None

    lm = db.current_claims(conn, LM)["parameters"]
    assert lm["status"] == "publisher_declared"
    assert lm["value"] == 8030261248


def test_claims_table_rejects_update_and_delete(project, conn, client):
    run_discover(project, conn, client)
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("UPDATE claims SET value = '\"x\"'")
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("DELETE FROM claims")


def test_retry_recovers_from_server_errors_but_not_from_404():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise HubError("HTTP 503", 503)
        return "ok"

    assert with_retry(flaky, sleep=no_sleep) == "ok"
    assert calls["n"] == 3

    def missing():
        calls["n"] += 1
        raise HubError("HTTP 404", 404)

    calls["n"] = 0
    with pytest.raises(HubError):
        with_retry(missing, sleep=no_sleep)
    assert calls["n"] == 1
