"""Search/filter/sort/pagination (goal 6) and approver assignment (goal 5)."""
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


def create_report(client, owner, title, start="2026-01-01", end="2026-01-02"):
    r = client.post(
        "/reports",
        json={"title": title, "start_date": start, "end_date": end},
        headers=auth_headers(owner),
    )
    assert r.status_code == 201
    return r.json()["id"]


def test_title_search(client, make_user):
    alice = make_user()
    create_report(client, alice, "Chicago conference")
    create_report(client, alice, "NYC client visit")

    r = client.get("/reports?q=chicago", headers=auth_headers(alice))
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Chicago conference"


def test_whitespace_only_search_behaves_like_no_search(client, make_user):
    """Regression test: q='   ' was being used literally in the ILIKE pattern
    (three spaces cannot appear in a title with single-spaced words), silently
    returning zero results - breaking the documented promise that an empty search
    means no filter, not a query that matches nothing. An accidental space in the
    search box is an easy real mistake, not just a theoretical one."""
    alice = make_user()
    create_report(client, alice, "Chicago conference")
    create_report(client, alice, "NYC client visit")

    r = client.get("/reports?q=%20%20%20", headers=auth_headers(alice))
    assert r.json()["total"] == 2

    # Surrounding whitespace around a real term is also trimmed, not treated as
    # part of the search text.
    r = client.get("/reports?q=%20chicago%20", headers=auth_headers(alice))
    assert r.json()["total"] == 1


def test_status_filter(client, make_user):
    alice = make_user()
    draft_id = create_report(client, alice, "Draft report")
    submitted_id = create_report(client, alice, "Submitted report")
    client.post(f"/reports/{submitted_id}/submit", headers=auth_headers(alice))

    r = client.get("/reports?status=draft", headers=auth_headers(alice))
    ids = [item["id"] for item in r.json()["items"]]
    assert draft_id in ids and submitted_id not in ids

    r = client.get("/reports?status=submitted", headers=auth_headers(alice))
    ids = [item["id"] for item in r.json()["items"]]
    assert submitted_id in ids and draft_id not in ids


def test_zero_hit_filter_is_empty_not_error(client, make_user):
    alice = make_user()
    create_report(client, alice, "Some report")
    r = client.get("/reports?q=nonexistent-title-xyz", headers=auth_headers(alice))
    assert r.status_code == 200
    assert r.json()["items"] == []
    assert r.json()["total"] == 0


def test_pagination_and_total_count(client, make_user):
    alice = make_user()
    for i in range(5):
        create_report(client, alice, f"Report {i}")

    r = client.get("/reports?page=1&page_size=2", headers=auth_headers(alice))
    body = r.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2

    r = client.get("/reports?page=3&page_size=2", headers=auth_headers(alice))
    body = r.json()
    assert len(body["items"]) == 1  # last partial page

    # out-of-range page: empty items, correct total, not an error
    r = client.get("/reports?page=50&page_size=2", headers=auth_headers(alice))
    assert r.status_code == 200
    assert r.json()["items"] == []
    assert r.json()["total"] == 5


def test_sort_by_total_amount(client, make_user):
    alice = make_user()
    small_id = create_report(client, alice, "Small")
    big_id = create_report(client, alice, "Big")
    client.post(
        f"/reports/{small_id}/lines",
        json={"date": "2026-01-01", "category": "travel", "amount_cents": 100, "description": "x"},
        headers=auth_headers(alice),
    )
    client.post(
        f"/reports/{big_id}/lines",
        json={"date": "2026-01-01", "category": "travel", "amount_cents": 99999, "description": "x"},
        headers=auth_headers(alice),
    )

    r = client.get("/reports?sort=total_cents&sort_dir=desc", headers=auth_headers(alice))
    ids = [item["id"] for item in r.json()["items"]]
    assert ids.index(big_id) < ids.index(small_id)


def test_invalid_sort_field_rejected(client, make_user):
    alice = make_user()
    r = client.get("/reports?sort=not_a_real_column", headers=auth_headers(alice))
    assert r.status_code == 422  # allow-listed via a Literal type, not raw SQL


def test_owner_and_approver_filters(client, make_user):
    alice = make_user()
    bob = make_user()
    carol = make_user(role=Role.approver)

    alice_report = create_report(client, alice, "Alice's report")
    client.post(f"/reports/{alice_report}/submit", headers=auth_headers(alice))
    create_report(client, bob, "Bob's report")  # left as a draft - shouldn't show up either way

    r = client.get(f"/reports?owner_id={alice.id}", headers=auth_headers(carol))
    ids = [item["id"] for item in r.json()["items"]]
    assert ids == [alice_report]

    # Assign carol to alice's report, then filter by approver_id.
    client.put(
        f"/reports/{alice_report}/approvers",
        json={"approver_ids": [carol.id]},
        headers=auth_headers(carol),
    )
    r = client.get(f"/reports?approver_id={carol.id}", headers=auth_headers(carol))
    ids = [item["id"] for item in r.json()["items"]]
    assert ids == [alice_report]


def test_assigned_to_me_filter(client, make_user):
    alice = make_user()
    carol = make_user(role=Role.approver)
    dave = make_user(role=Role.approver)

    report_id = create_report(client, alice, "Needs review")
    client.post(f"/reports/{report_id}/submit", headers=auth_headers(alice))
    client.put(
        f"/reports/{report_id}/approvers",
        json={"approver_ids": [dave.id]},
        headers=auth_headers(dave),
    )

    r = client.get("/reports?assigned_to_me=true", headers=auth_headers(dave))
    assert any(item["id"] == report_id for item in r.json()["items"])

    r = client.get("/reports?assigned_to_me=true", headers=auth_headers(carol))
    assert all(item["id"] != report_id for item in r.json()["items"])


def test_set_approvers_rejects_non_approver_ids(client, make_user):
    alice = make_user()
    bob_employee = make_user()
    carol = make_user(role=Role.approver)
    report_id = create_report(client, alice, "Trip")
    client.post(f"/reports/{report_id}/submit", headers=auth_headers(alice))

    r = client.put(
        f"/reports/{report_id}/approvers",
        json={"approver_ids": [bob_employee.id]},
        headers=auth_headers(carol),
    )
    assert r.status_code == 400


def test_owner_can_set_own_approvers(client, make_user):
    """The report's own owner can manage its assignments too, even without the
    approver role - routing your own report to whoever should review it is
    reasonable, and it grants no actual power: decide()/mark_paid() re-check
    ownership independently regardless of who's assigned, so this can't be used
    as a self-approval backdoor."""
    alice = make_user()
    carol = make_user(role=Role.approver)
    report_id = create_report(client, alice, "Trip")

    r = client.put(
        f"/reports/{report_id}/approvers",
        json={"approver_ids": [carol.id]},
        headers=auth_headers(alice),
    )
    assert r.status_code == 200
    assert [a["id"] for a in r.json()["approvers"]] == [carol.id]


def test_set_approvers_requires_approver_role_or_ownership(client, make_user):
    """A plain employee who neither owns the report nor holds the approver role
    still can't touch its assignments - in practice this is 404, not 403, since
    get_visible_report already blocks an outsider from seeing the report at all
    (an employee has never been able to see another employee's reports in any
    status). The explicit role-or-owner check inside set_approvers itself is
    consequently unreachable via this route today - kept anyway as the actual,
    self-documenting authorization rule rather than relying on a reader to infer
    it from get_visible_report's separate visibility logic."""
    alice = make_user()
    bob = make_user()
    report_id = create_report(client, alice, "Trip")
    r = client.put(
        f"/reports/{report_id}/approvers",
        json={"approver_ids": []},
        headers=auth_headers(bob),
    )
    assert r.status_code == 404


def test_list_approvers_endpoint(client, make_user):
    make_user()  # an employee, should not appear
    carol = make_user(role=Role.approver, name="Carol")
    dave = make_user(role=Role.approver, name="Dave")

    r = client.get("/reports/approvers", headers=auth_headers(carol))
    assert r.status_code == 200
    names = {u["name"] for u in r.json()}
    assert names == {"Carol", "Dave"}


def test_duplicate_approver_id_is_idempotent(client, make_user):
    alice = make_user()
    carol = make_user(role=Role.approver)
    report_id = create_report(client, alice, "Trip")
    client.post(f"/reports/{report_id}/submit", headers=auth_headers(alice))

    r = client.put(
        f"/reports/{report_id}/approvers",
        json={"approver_ids": [carol.id, carol.id, carol.id]},
        headers=auth_headers(carol),
    )
    assert r.status_code == 200
    assert [a["id"] for a in r.json()["approvers"]] == [carol.id]  # not duplicated
