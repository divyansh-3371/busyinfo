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
    assert any(item["id"] == report_id for item in r.json()["items"])

    # Bob (a different employee) does not.
    r = client.get("/reports", headers=auth_headers(bob))
    assert all(item["id"] != report_id for item in r.json()["items"])

    # Bob also can't fetch it directly - 404, not 403 (don't confirm it exists).
    r = client.get(f"/reports/{report_id}", headers=auth_headers(bob))
    assert r.status_code == 404


def test_approver_sees_submitted_reports_but_not_drafts(client, make_user):
    """Regression test: an approver used to see every report regardless of
    status, including another employee's still-being-edited Draft - a Draft is
    the owner's private, unfinished work, and the brief's own wording ("reports
    submitted by other employees") never included seeing it before that."""
    alice = make_user()
    carol = make_user(role=Role.approver)

    report_id = client.post(
        "/reports",
        json={"title": "Trip", "start_date": "2026-01-01", "end_date": "2026-01-02"},
        headers=auth_headers(alice),
    ).json()["id"]

    # Still a Draft - invisible to another approver, in both the list and by id.
    r = client.get("/reports", headers=auth_headers(carol))
    assert all(item["id"] != report_id for item in r.json()["items"])
    r = client.get(f"/reports/{report_id}", headers=auth_headers(carol))
    assert r.status_code == 404

    # Once submitted, both become visible.
    client.post(f"/reports/{report_id}/submit", headers=auth_headers(alice))
    r = client.get("/reports", headers=auth_headers(carol))
    assert any(item["id"] == report_id for item in r.json()["items"])
    r = client.get(f"/reports/{report_id}", headers=auth_headers(carol))
    assert r.status_code == 200


def test_approver_always_sees_their_own_reports_including_drafts(client, make_user):
    """An approver is also an employee for their own reports - the "no drafts
    visible to others" rule must never apply to a report you own yourself."""
    carol = make_user(role=Role.approver)
    report_id = client.post(
        "/reports",
        json={"title": "My own draft", "start_date": "2026-01-01", "end_date": "2026-01-02"},
        headers=auth_headers(carol),
    ).json()["id"]

    r = client.get("/reports", headers=auth_headers(carol))
    assert any(item["id"] == report_id for item in r.json()["items"])
    r = client.get(f"/reports/{report_id}", headers=auth_headers(carol))
    assert r.status_code == 200


def test_approver_who_decided_keeps_seeing_the_report_after_it_becomes_a_draft(client, make_user):
    """A rejecting approver's own past decision stays visible to them, even once
    the report bounces back to Draft - a narrow exception to "drafts are private,"
    not a rollback of it: a *different*, uninvolved approver still can't see it."""
    alice = make_user()
    carol = make_user(role=Role.approver)
    dave = make_user(role=Role.approver)

    report_id = client.post(
        "/reports",
        json={"title": "Trip", "start_date": "2026-01-01", "end_date": "2026-01-02"},
        headers=auth_headers(alice),
    ).json()["id"]
    client.post(
        f"/reports/{report_id}/lines",
        json={"date": "2026-01-01", "category": "travel", "amount_cents": 1000, "description": "Cab"},
        headers=auth_headers(alice),
    )
    client.post(f"/reports/{report_id}/submit", headers=auth_headers(alice))
    client.post(
        f"/reports/{report_id}/decide",
        json={"decision": "rejected", "reason": "Missing receipt"},
        headers=auth_headers(carol),
    )

    # Carol rejected it - she can still see it now that it's back in Draft.
    r = client.get(f"/reports/{report_id}", headers=auth_headers(carol))
    assert r.status_code == 200
    assert r.json()["status"] == "draft"

    # The frozen snapshot of what she actually rejected is right there in her
    # own timeline entry.
    reject_event = next(e for e in r.json()["status_events"] if e["to_status"] == "rejected")
    assert reject_event["line_snapshot"] == [
        {
            "date": "2026-01-01", "category": "travel", "amount_cents": 1000,
            "description": "Cab", "other_category_note": None,
        }
    ]

    # Dave never touched this report - still invisible to him while it's a draft.
    r = client.get(f"/reports/{report_id}", headers=auth_headers(dave))
    assert r.status_code == 404

    # Alice edits the line and resubmits - carol's frozen snapshot doesn't move,
    # even though the report's own live lines now show the new amount.
    line_id = client.get(f"/reports/{report_id}", headers=auth_headers(alice)).json()["lines"][0]["id"]
    client.patch(
        f"/reports/{report_id}/lines/{line_id}",
        json={"date": "2026-01-01", "category": "travel", "amount_cents": 5000, "description": "Cab (fixed)"},
        headers=auth_headers(alice),
    )
    client.post(f"/reports/{report_id}/submit", headers=auth_headers(alice))

    r = client.get(f"/reports/{report_id}", headers=auth_headers(carol))
    assert r.status_code == 200
    assert r.json()["status"] == "submitted"
    assert r.json()["lines"][0]["amount_cents"] == 5000  # the live, current data
    reject_event = next(e for e in r.json()["status_events"] if e["to_status"] == "rejected")
    assert reject_event["line_snapshot"][0]["amount_cents"] == 1000  # still the old, rejected version


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


def test_line_other_category_note_is_optional(client, make_user):
    """The fixed category list can't name everything; other_category_note lets a
    line elaborate when category="other" without being required - unlike
    description, which is required on every line regardless of category."""
    alice = make_user()
    report_id = client.post(
        "/reports",
        json={"title": "Trip", "start_date": "2026-01-01", "end_date": "2026-01-02"},
        headers=auth_headers(alice),
    ).json()["id"]

    # Omitted entirely - still works, comes back null, not required.
    r = client.post(
        f"/reports/{report_id}/lines",
        json={"date": "2026-01-01", "category": "other", "amount_cents": 500, "description": "Misc"},
        headers=auth_headers(alice),
    )
    assert r.status_code == 201
    assert r.json()["other_category_note"] is None

    # Provided - comes back as given.
    r = client.post(
        f"/reports/{report_id}/lines",
        json={
            "date": "2026-01-01",
            "category": "other",
            "amount_cents": 750,
            "description": "Misc",
            "other_category_note": "Parking permit",
        },
        headers=auth_headers(alice),
    )
    assert r.status_code == 201
    assert r.json()["other_category_note"] == "Parking permit"

    # Whitespace-only counts as "didn't fill it in", not an empty string saved.
    r = client.post(
        f"/reports/{report_id}/lines",
        json={
            "date": "2026-01-01",
            "category": "other",
            "amount_cents": 250,
            "description": "Misc",
            "other_category_note": "   ",
        },
        headers=auth_headers(alice),
    )
    assert r.status_code == 201
    assert r.json()["other_category_note"] is None


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


def test_needs_attention_count_only_counts_rejected_drafts(client, make_user):
    """The nav badge for 'a rejection needs your attention' - distinct from
    ordinary Drafts a user just hasn't submitted yet, which shouldn't count."""
    alice = make_user()
    carol = make_user(role=Role.approver)

    def count_for(user) -> int:
        return client.get("/reports/needs-attention-count", headers=auth_headers(user)).json()["count"]

    # A brand-new, never-submitted draft doesn't count.
    client.post(
        "/reports",
        json={"title": "Never submitted", "start_date": "2026-01-01", "end_date": "2026-01-02"},
        headers=auth_headers(alice),
    )
    assert count_for(alice) == 0

    # Submit and reject one - now it does.
    report_id = client.post(
        "/reports",
        json={"title": "Will be rejected", "start_date": "2026-01-01", "end_date": "2026-01-02"},
        headers=auth_headers(alice),
    ).json()["id"]
    client.post(f"/reports/{report_id}/submit", headers=auth_headers(alice))
    client.post(
        f"/reports/{report_id}/decide",
        json={"decision": "rejected", "reason": "Missing receipt"},
        headers=auth_headers(carol),
    )
    assert count_for(alice) == 1
    assert count_for(carol) == 0  # it's alice's report, not carol's

    # Resubmitting it clears the count - the natural fix, not a separate dismiss.
    client.post(f"/reports/{report_id}/submit", headers=auth_headers(alice))
    assert count_for(alice) == 0


def test_needs_attention_flag_shows_on_the_report_and_clears_only_on_resubmit(client, make_user):
    """The per-row "rejected" mark the owner sees in their reports list. Viewing
    the report - by the owner or by the rejecting approver - must NOT clear it:
    reading the rejection reason is the first thing an owner does, and if that
    same GET wiped the mark, it would vanish before it's ever seen in the list.
    It only clears once the owner actually resubmits a fix."""
    alice = make_user()
    carol = make_user(role=Role.approver)
    report_id = client.post(
        "/reports",
        json={"title": "Trip", "start_date": "2026-01-01", "end_date": "2026-01-02"},
        headers=auth_headers(alice),
    ).json()["id"]
    client.post(
        f"/reports/{report_id}/lines",
        json={"date": "2026-01-01", "category": "meals", "amount_cents": 500, "description": "lunch"},
        headers=auth_headers(alice),
    )
    client.post(f"/reports/{report_id}/submit", headers=auth_headers(alice))
    client.post(
        f"/reports/{report_id}/decide",
        json={"decision": "rejected", "reason": "Missing receipt"},
        headers=auth_headers(carol),
    )

    # Shows up on the report itself, and in the reports list.
    assert client.get(f"/reports/{report_id}", headers=auth_headers(carol)).json()["needs_owner_attention"] is True
    listed = client.get("/reports", headers=auth_headers(alice)).json()["items"]
    assert next(r for r in listed if r["id"] == report_id)["needs_owner_attention"] is True

    # The "rejected" status filter surfaces it too, for both alice and carol -
    # since a report's real status is never actually "rejected" (it's already
    # back to draft), this filter is defined in terms of the flag instead.
    for u in (alice, carol):
        filtered = client.get("/reports?status=rejected", headers=auth_headers(u)).json()["items"]
        assert any(r["id"] == report_id for r in filtered)

    # Carol (the rejecting approver, viewing via her permanent decision-access)
    # opening it does NOT clear alice's mark.
    client.get(f"/reports/{report_id}", headers=auth_headers(carol))
    assert client.get(
        "/reports", headers=auth_headers(alice)
    ).json()["items"][0]["needs_owner_attention"] is True

    # Alice opening it - even repeatedly - does NOT clear it either.
    client.get(f"/reports/{report_id}", headers=auth_headers(alice))
    client.get(f"/reports/{report_id}", headers=auth_headers(alice))
    assert client.get(f"/reports/{report_id}", headers=auth_headers(alice)).json()["needs_owner_attention"] is True

    # Only resubmitting clears it, and it drops out of the "rejected" filter.
    client.post(f"/reports/{report_id}/submit", headers=auth_headers(alice))
    filtered = client.get("/reports?status=rejected", headers=auth_headers(alice)).json()["items"]
    assert not any(r["id"] == report_id for r in filtered)


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
    assert all(item["id"] != report_id for item in r.json()["items"])
    # ...but included when asked for explicitly.
    r = client.get("/reports?include_archived=true", headers=auth_headers(alice))
    assert any(item["id"] == report_id for item in r.json()["items"])

    # Double-archive is a clean 400, not a crash.
    r = client.post(f"/reports/{report_id}/archive", headers=auth_headers(alice))
    assert r.status_code == 400

    r = client.post(f"/reports/{report_id}/restore", headers=auth_headers(alice))
    assert r.status_code == 200
    assert r.json()["archived_at"] is None


def test_archiving_a_rejected_report_clears_the_needs_attention_mark(client, make_user):
    """Archiving is itself a resolution - the owner has decided to walk away
    from this one rather than fix and resubmit it, so it shouldn't keep
    flagging the nav badge or needs-attention count."""
    alice = make_user()
    carol = make_user(role=Role.approver)
    report_id = client.post(
        "/reports",
        json={"title": "Trip", "start_date": "2026-01-01", "end_date": "2026-01-02"},
        headers=auth_headers(alice),
    ).json()["id"]
    client.post(
        f"/reports/{report_id}/lines",
        json={"date": "2026-01-01", "category": "meals", "amount_cents": 500, "description": "lunch"},
        headers=auth_headers(alice),
    )
    client.post(f"/reports/{report_id}/submit", headers=auth_headers(alice))
    client.post(
        f"/reports/{report_id}/decide",
        json={"decision": "rejected", "reason": "Missing receipt"},
        headers=auth_headers(carol),
    )
    assert (
        client.get("/reports/needs-attention-count", headers=auth_headers(alice)).json()["count"]
        == 1
    )

    r = client.post(f"/reports/{report_id}/archive", headers=auth_headers(alice))
    assert r.json()["needs_owner_attention"] is False
    assert (
        client.get("/reports/needs-attention-count", headers=auth_headers(alice)).json()["count"]
        == 0
    )
    # And it no longer shows under the "rejected" filter either, archived or not.
    r = client.get("/reports?status=rejected&include_archived=true", headers=auth_headers(alice))
    assert all(item["id"] != report_id for item in r.json()["items"])


def test_401_without_token(client):
    r = client.get("/reports")
    assert r.status_code == 401


def test_cannot_edit_report_metadata_after_submit(client, make_user):
    alice = make_user()
    report_id = client.post(
        "/reports",
        json={"title": "Trip", "start_date": "2026-01-01", "end_date": "2026-01-02"},
        headers=auth_headers(alice),
    ).json()["id"]
    client.post(f"/reports/{report_id}/submit", headers=auth_headers(alice))

    r = client.patch(
        f"/reports/{report_id}", json={"title": "Renamed"}, headers=auth_headers(alice)
    )
    assert r.status_code == 400


def test_archived_report_still_viewable_via_detail(client, make_user):
    alice = make_user()
    report_id = client.post(
        "/reports",
        json={"title": "Trip", "start_date": "2026-01-01", "end_date": "2026-01-02"},
        headers=auth_headers(alice),
    ).json()["id"]
    client.post(f"/reports/{report_id}/archive", headers=auth_headers(alice))

    r = client.get(f"/reports/{report_id}", headers=auth_headers(alice))
    assert r.status_code == 200
    assert r.json()["archived_at"] is not None


def test_line_rejects_absurdly_large_amount(client, make_user):
    alice = make_user()
    report_id = client.post(
        "/reports",
        json={"title": "Trip", "start_date": "2026-01-01", "end_date": "2026-01-02"},
        headers=auth_headers(alice),
    ).json()["id"]
    r = client.post(
        f"/reports/{report_id}/lines",
        json={
            "date": "2026-01-01",
            "category": "travel",
            "amount_cents": 999_999_999_999,
            "description": "x",
        },
        headers=auth_headers(alice),
    )
    assert r.status_code == 422


def test_line_rejects_invalid_category_and_date(client, make_user):
    alice = make_user()
    report_id = client.post(
        "/reports",
        json={"title": "Trip", "start_date": "2026-01-01", "end_date": "2026-01-02"},
        headers=auth_headers(alice),
    ).json()["id"]
    r = client.post(
        f"/reports/{report_id}/lines",
        json={"date": "2026-01-01", "category": "not-a-real-category", "amount_cents": 100, "description": "x"},
        headers=auth_headers(alice),
    )
    assert r.status_code == 422
    r = client.post(
        f"/reports/{report_id}/lines",
        json={"date": "not-a-date", "category": "travel", "amount_cents": 100, "description": "x"},
        headers=auth_headers(alice),
    )
    assert r.status_code == 422


def test_delete_line_recomputes_total(client, make_user):
    alice = make_user()
    report_id = client.post(
        "/reports",
        json={"title": "Trip", "start_date": "2026-01-01", "end_date": "2026-01-02"},
        headers=auth_headers(alice),
    ).json()["id"]
    line_id = client.post(
        f"/reports/{report_id}/lines",
        json={"date": "2026-01-01", "category": "travel", "amount_cents": 1000, "description": "x"},
        headers=auth_headers(alice),
    ).json()["id"]
    client.post(
        f"/reports/{report_id}/lines",
        json={"date": "2026-01-01", "category": "meals", "amount_cents": 500, "description": "y"},
        headers=auth_headers(alice),
    )

    r = client.delete(f"/reports/{report_id}/lines/{line_id}", headers=auth_headers(alice))
    assert r.status_code == 204

    detail = client.get(f"/reports/{report_id}", headers=auth_headers(alice)).json()
    assert detail["total_cents"] == 500
    assert len(detail["lines"]) == 1


def test_update_line_recomputes_total(client, make_user):
    """Regression test: update_line was missing the db.flush() that add_line and
    delete_line both have before recalculate_total, so editing a line's amount left
    the report's total_cents using the line's *old* amount - wrong, and permanently
    committed. Caught by tightening the test session to match production's real
    autoflush=False rather than by this test alone; kept here as the concrete,
    goal-3-shaped regression check."""
    alice = make_user()
    report_id = client.post(
        "/reports",
        json={"title": "Trip", "start_date": "2026-01-01", "end_date": "2026-01-02"},
        headers=auth_headers(alice),
    ).json()["id"]
    line_id = client.post(
        f"/reports/{report_id}/lines",
        json={"date": "2026-01-01", "category": "travel", "amount_cents": 1000, "description": "x"},
        headers=auth_headers(alice),
    ).json()["id"]
    client.post(
        f"/reports/{report_id}/lines",
        json={"date": "2026-01-01", "category": "meals", "amount_cents": 500, "description": "y"},
        headers=auth_headers(alice),
    )

    r = client.patch(
        f"/reports/{report_id}/lines/{line_id}",
        json={"date": "2026-01-01", "category": "travel", "amount_cents": 4000, "description": "x"},
        headers=auth_headers(alice),
    )
    assert r.status_code == 200

    detail = client.get(f"/reports/{report_id}", headers=auth_headers(alice)).json()
    assert detail["total_cents"] == 4500  # 4000 (edited) + 500, not 1000 + 500


def test_zero_line_report_can_be_submitted(client, make_user):
    """Documented assumption: a report with no lines can still be
    submitted, with a total of 0 - not silently blocked."""
    alice = make_user()
    report_id = client.post(
        "/reports",
        json={"title": "Empty report", "start_date": "2026-01-01", "end_date": "2026-01-02"},
        headers=auth_headers(alice),
    ).json()["id"]
    r = client.post(f"/reports/{report_id}/submit", headers=auth_headers(alice))
    assert r.status_code == 200
    assert r.json()["total_cents"] == 0
