"""Bulk approve/reject (goal 7): every report checked individually, self-owned
failures labeled distinctly, plus the CSV export of approved-but-unpaid reports."""
import csv
import io

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app
from app.models.enums import Role


@pytest.fixture()
def client(db):
    from app.db.session import get_db

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()


def auth_headers(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=user.id)}"}


def create_submitted_report(client, owner, title="Trip"):
    report_id = client.post(
        "/reports",
        json={"title": title, "start_date": "2026-01-01", "end_date": "2026-01-02"},
        headers=auth_headers(owner),
    ).json()["id"]
    client.post(f"/reports/{report_id}/submit", headers=auth_headers(owner))
    return report_id


def test_bulk_approve_mixed_batch(client, make_user):
    alice = make_user()
    bob = make_user()
    carol = make_user(role=Role.approver)

    alice_report = create_submitted_report(client, alice, "Alice's trip")
    bob_report = create_submitted_report(client, bob, "Bob's trip")
    carols_own_report = create_submitted_report(client, carol, "Carol's own trip")

    r = client.post(
        "/reports/bulk-decide",
        json={
            "report_ids": [alice_report, bob_report, carols_own_report, 999999],
            "decision": "approved",
        },
        headers=auth_headers(carol),
    )
    assert r.status_code == 200
    results = {item["report_id"]: item for item in r.json()["results"]}

    assert results[alice_report]["ok"] is True
    assert results[bob_report]["ok"] is True
    assert results[carols_own_report]["ok"] is False
    assert results[carols_own_report]["self_owned"] is True
    assert results[999999]["ok"] is False
    assert results[999999]["self_owned"] is False

    # The two legitimate approvals actually took effect despite the other failures.
    assert client.get(f"/reports/{alice_report}", headers=auth_headers(carol)).json()["status"] == (
        "approved"
    )
    assert client.get(f"/reports/{bob_report}", headers=auth_headers(carol)).json()["status"] == (
        "approved"
    )


def test_bulk_reject_requires_reason(client, make_user):
    alice = make_user()
    carol = make_user(role=Role.approver)
    report_id = create_submitted_report(client, alice)

    r = client.post(
        "/reports/bulk-decide",
        json={"report_ids": [report_id], "decision": "rejected"},
        headers=auth_headers(carol),
    )
    result = r.json()["results"][0]
    assert result["ok"] is False
    assert result["self_owned"] is False


def test_bulk_decide_empty_selection_rejected(client, make_user):
    carol = make_user(role=Role.approver)
    r = client.post(
        "/reports/bulk-decide",
        json={"report_ids": [], "decision": "approved"},
        headers=auth_headers(carol),
    )
    assert r.status_code == 400


def test_bulk_decide_requires_approver_role(client, make_user):
    alice = make_user()
    r = client.post(
        "/reports/bulk-decide",
        json={"report_ids": [1], "decision": "approved"},
        headers=auth_headers(alice),
    )
    assert r.status_code == 403


def test_export_due_csv(client, make_user):
    alice = make_user()
    carol = make_user(role=Role.approver)
    report_id = create_submitted_report(client, alice, "Due trip")
    client.post(f"/reports/{report_id}/decide", json={"decision": "approved"}, headers=auth_headers(carol))

    r = client.get("/reports/export-due", headers=auth_headers(carol))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")

    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0] == [
        "report_id", "title", "owner_name", "owner_email", "total_usd", "start_date", "end_date", "submitted_at",
    ]
    assert any(row[0] == str(report_id) for row in rows[1:])


def test_export_due_csv_empty_is_header_only(client, make_user):
    carol = make_user(role=Role.approver)
    r = client.get("/reports/export-due", headers=auth_headers(carol))
    assert r.status_code == 200
    rows = list(csv.reader(io.StringIO(r.text)))
    assert len(rows) == 1  # header only, not an empty/broken file


def test_export_due_requires_approver_role(client, make_user):
    alice = make_user()
    r = client.get("/reports/export-due", headers=auth_headers(alice))
    assert r.status_code == 403
