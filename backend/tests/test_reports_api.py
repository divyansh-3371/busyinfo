"""API-level tests: full HTTP round trips through FastAPI's TestClient against the
real test Postgres database (see conftest.py), covering report/line CRUD, the
lifecycle endpoints, and the visibility/authorization edge cases that matter most."""
import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app
from app.models.enums import Role


@pytest.fixture()
def client(db, monkeypatch):
    """Overrides the app's get_db dependency to use the same per-test transaction as
    everything else, so API calls and direct DB assertions see the same data."""
    from app.db.session import get_db

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()


def auth_headers(user) -> dict:
    token = create_access_token(subject=user.id)
    return {"Authorization": f"Bearer {token}"}


def test_create_and_list_report_scoped_to_owner(client, make_user):
    alice = make_user()
    bob = make_user()

    r = client.post(
        "/reports",
        json={"title": "Trip", "start_date": "2026-01-01", "end_date": "2026-01-02"},
        headers=auth_headers(alice),
    )
    assert r.status_code == 201
    report_id = r.json()["id"]

    # Alice sees it in her list.
    r = client.get("/reports", headers=auth_headers(alice))
    assert any(item["id"] == report_id for item in r.json())

    # Bob (a different employee) does not.
    r = client.get("/reports", headers=auth_headers(bob))
    assert all(item["id"] != report_id for item in r.json())

    # Bob also can't fetch it directly - 404, not 403 (don't confirm it exists).
    r = client.get(f"/reports/{report_id}", headers=auth_headers(bob))
    assert r.status_code == 404


def test_approver_sees_everyone_reports(client, make_user):
    alice = make_user()
    carol = make_user(role=Role.approver)

    r = client.post(
        "/reports",
        json={"title": "Trip", "start_date": "2026-01-01", "end_date": "2026-01-02"},
        headers=auth_headers(alice),
    )
    report_id = r.json()["id"]

    r = client.get("/reports", headers=auth_headers(carol))
    assert any(item["id"] == report_id for item in r.json())

    r = client.get(f"/reports/{report_id}", headers=auth_headers(carol))
    assert r.status_code == 200


def test_report_creation_rejects_bad_input(client, make_user):
    alice = make_user()
    # blank title
    r = client.post(
        "/reports",
        json={"title": "   ", "start_date": "2026-01-01", "end_date": "2026-01-02"},
        headers=auth_headers(alice),
    )
    assert r.status_code == 422
    # end before start
    r = client.post(
        "/reports",
        json={"title": "Trip", "start_date": "2026-01-05", "end_date": "2026-01-01"},
        headers=auth_headers(alice),
    )
    assert r.status_code == 422


def test_add_line_and_total_recomputed(client, make_user):
    alice = make_user()
    report_id = client.post(
        "/reports",
        json={"title": "Trip", "start_date": "2026-01-01", "end_date": "2026-01-02"},
        headers=auth_headers(alice),
    ).json()["id"]

    r = client.post(
        f"/reports/{report_id}/lines",
        json={"date": "2026-01-01", "category": "travel", "amount_cents": 1000, "description": "Cab"},
        headers=auth_headers(alice),
    )
    assert r.status_code == 201
    r = client.post(
        f"/reports/{report_id}/lines",
        json={"date": "2026-01-01", "category": "meals", "amount_cents": 2500, "description": "Lunch"},
        headers=auth_headers(alice),
    )
    assert r.status_code == 201

    detail = client.get(f"/reports/{report_id}", headers=auth_headers(alice)).json()
    assert detail["total_cents"] == 3500
    assert len(detail["lines"]) == 2


def test_line_rejects_non_positive_amount(client, make_user):
    alice = make_user()
    report_id = client.post(
        "/reports",
        json={"title": "Trip", "start_date": "2026-01-01", "end_date": "2026-01-02"},
        headers=auth_headers(alice),
    ).json()["id"]

    for bad_amount in (0, -500):
        r = client.post(
            f"/reports/{report_id}/lines",
            json={
                "date": "2026-01-01",
                "category": "travel",
                "amount_cents": bad_amount,
                "description": "x",
            },
            headers=auth_headers(alice),
        )
        assert r.status_code == 422


def test_cannot_edit_lines_after_submit(client, make_user):
    alice = make_user()
    report_id = client.post(
        "/reports",
        json={"title": "Trip", "start_date": "2026-01-01", "end_date": "2026-01-02"},
        headers=auth_headers(alice),
    ).json()["id"]
    client.post(
        f"/reports/{report_id}/lines",
        json={"date": "2026-01-01", "category": "travel", "amount_cents": 1000, "description": "x"},
        headers=auth_headers(alice),
    )
    r = client.post(f"/reports/{report_id}/submit", headers=auth_headers(alice))
    assert r.status_code == 200
    assert r.json()["status"] == "submitted"

    r = client.post(
        f"/reports/{report_id}/lines",
        json={"date": "2026-01-01", "category": "travel", "amount_cents": 500, "description": "y"},
        headers=auth_headers(alice),
    )
    assert r.status_code == 400


def test_full_lifecycle_walk(client, make_user):
    alice = make_user()
    carol = make_user(role=Role.approver)

    report_id = client.post(
        "/reports",
        json={"title": "Trip", "start_date": "2026-01-01", "end_date": "2026-01-02"},
        headers=auth_headers(alice),
    ).json()["id"]
    client.post(
        f"/reports/{report_id}/lines",
        json={"date": "2026-01-01", "category": "travel", "amount_cents": 1000, "description": "x"},
        headers=auth_headers(alice),
    )
    assert client.post(f"/reports/{report_id}/submit", headers=auth_headers(alice)).status_code == 200

    r = client.post(
        f"/reports/{report_id}/decide",
        json={"decision": "approved"},
        headers=auth_headers(carol),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "approved"

    r = client.post(f"/reports/{report_id}/pay", headers=auth_headers(carol))
    assert r.status_code == 200
    assert r.json()["status"] == "paid"


def test_self_approval_blocked_via_http(client, make_user):
    carol = make_user(role=Role.approver)
    report_id = client.post(
        "/reports",
        json={"title": "Carol's own", "start_date": "2026-01-01", "end_date": "2026-01-02"},
        headers=auth_headers(carol),
    ).json()["id"]
    client.post(f"/reports/{report_id}/submit", headers=auth_headers(carol))

    r = client.post(
        f"/reports/{report_id}/decide",
        json={"decision": "approved"},
        headers=auth_headers(carol),
    )
    assert r.status_code == 400
    assert "own" in r.json()["detail"].lower()


def test_reject_requires_reason_via_http(client, make_user):
    alice = make_user()
    carol = make_user(role=Role.approver)
    report_id = client.post(
        "/reports",
        json={"title": "Trip", "start_date": "2026-01-01", "end_date": "2026-01-02"},
        headers=auth_headers(alice),
    ).json()["id"]
    client.post(f"/reports/{report_id}/submit", headers=auth_headers(alice))

    r = client.post(
        f"/reports/{report_id}/decide",
        json={"decision": "rejected"},
        headers=auth_headers(carol),
    )
    assert r.status_code == 400

    r = client.post(
        f"/reports/{report_id}/decide",
        json={"decision": "rejected", "reason": "Missing receipt"},
        headers=auth_headers(carol),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "draft"  # rejected reports return to draft automatically


def test_archive_and_restore(client, make_user):
    alice = make_user()
    report_id = client.post(
        "/reports",
        json={"title": "Trip", "start_date": "2026-01-01", "end_date": "2026-01-02"},
        headers=auth_headers(alice),
    ).json()["id"]

    r = client.post(f"/reports/{report_id}/archive", headers=auth_headers(alice))
    assert r.status_code == 200
    assert r.json()["archived_at"] is not None

    # Archived report is excluded from the default list...
    r = client.get("/reports", headers=auth_headers(alice))
    assert all(item["id"] != report_id for item in r.json())
    # ...but included when asked for explicitly.
    r = client.get("/reports?include_archived=true", headers=auth_headers(alice))
    assert any(item["id"] == report_id for item in r.json())

    # Double-archive is a clean 400, not a crash.
    r = client.post(f"/reports/{report_id}/archive", headers=auth_headers(alice))
    assert r.status_code == 400

    r = client.post(f"/reports/{report_id}/restore", headers=auth_headers(alice))
    assert r.status_code == 200
    assert r.json()["archived_at"] is None


def test_401_without_token(client):
    r = client.get("/reports")
    assert r.status_code == 401
