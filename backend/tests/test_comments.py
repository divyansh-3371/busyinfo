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


def test_owner_and_approver_can_comment(client, make_user):
    alice = make_user()
    carol = make_user(role=Role.approver)
    report_id = client.post(
        "/reports",
        json={"title": "Trip", "start_date": "2026-01-01", "end_date": "2026-01-02"},
        headers=auth_headers(alice),
    ).json()["id"]

    r = client.post(
        f"/reports/{report_id}/comments", json={"body": "Please review"}, headers=auth_headers(alice)
    )
    assert r.status_code == 201

    r = client.post(
        f"/reports/{report_id}/comments",
        json={"body": "Looks fine"},
        headers=auth_headers(carol),
    )
    assert r.status_code == 201

    detail = client.get(f"/reports/{report_id}", headers=auth_headers(alice)).json()
    assert [c["body"] for c in detail["comments"]] == ["Please review", "Looks fine"]


def test_other_employee_cannot_comment(client, make_user):
    alice = make_user()
    bob = make_user()
    report_id = client.post(
        "/reports",
        json={"title": "Trip", "start_date": "2026-01-01", "end_date": "2026-01-02"},
        headers=auth_headers(alice),
    ).json()["id"]

    r = client.post(
        f"/reports/{report_id}/comments", json={"body": "Snooping"}, headers=auth_headers(bob)
    )
    assert r.status_code == 404  # can't see the report at all


def test_blank_comment_rejected(client, make_user):
    alice = make_user()
    report_id = client.post(
        "/reports",
        json={"title": "Trip", "start_date": "2026-01-01", "end_date": "2026-01-02"},
        headers=auth_headers(alice),
    ).json()["id"]

    r = client.post(f"/reports/{report_id}/comments", json={"body": "   "}, headers=auth_headers(alice))
    assert r.status_code == 422


def test_no_edit_or_delete_route_exists(client, make_user):
    """Append-only: not one specific check but structural - there is no PATCH/DELETE
    at this path at all, so trying either falls through to a 405, never succeeding."""
    alice = make_user()
    report_id = client.post(
        "/reports",
        json={"title": "Trip", "start_date": "2026-01-01", "end_date": "2026-01-02"},
        headers=auth_headers(alice),
    ).json()["id"]
    comment_id = client.post(
        f"/reports/{report_id}/comments", json={"body": "Original"}, headers=auth_headers(alice)
    ).json()["id"]

    assert client.patch(
        f"/reports/{report_id}/comments/{comment_id}",
        json={"body": "Edited"},
        headers=auth_headers(alice),
    ).status_code in (404, 405)
    assert client.delete(
        f"/reports/{report_id}/comments/{comment_id}", headers=auth_headers(alice)
    ).status_code in (404, 405)
