"""Stale-approval alerts (goal 10) - unit tests on the date math with an injected
'now' (never real clock waits), plus API-level tests for the routes."""
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app
from app.models.enums import ReportStatus, Role
from app.models.report import ExpenseReport
from app.services import stale_alerts


def make_report(db, owner, *, status=ReportStatus.submitted, submitted_at=None) -> ExpenseReport:
    report = ExpenseReport(
        owner_id=owner.id,
        title="Test report",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 2),
        status=status,
        submitted_at=submitted_at,
    )
    db.add(report)
    db.flush()
    return report


# --- is_stale / get_alerts_for_approver: unit level ---


def test_not_yet_stale(db, make_user):
    owner = make_user()
    now = datetime(2026, 1, 10)
    report = make_report(db, owner, submitted_at=now - timedelta(days=2))
    assert stale_alerts.is_stale(report, now=now, stale_days=3) is False


def test_just_stale(db, make_user):
    owner = make_user()
    now = datetime(2026, 1, 10)
    report = make_report(db, owner, submitted_at=now - timedelta(days=3))
    assert stale_alerts.is_stale(report, now=now, stale_days=3) is True


def test_non_submitted_report_never_stale(db, make_user):
    owner = make_user()
    now = datetime(2026, 1, 10)
    report = make_report(
        db, owner, status=ReportStatus.approved, submitted_at=now - timedelta(days=30)
    )
    assert stale_alerts.is_stale(report, now=now, stale_days=3) is False


def test_dismissed_and_still_snoozed_excluded(db, make_user):
    owner = make_user()
    approver = make_user(role=Role.approver)
    now = datetime(2026, 1, 10)
    report = make_report(db, owner, submitted_at=now - timedelta(days=5))
    stale_alerts.dismiss(db, report, approver, now=now)

    alerts = stale_alerts.get_alerts_for_approver(db, approver, now=now + timedelta(hours=1))
    assert report.id not in [r.id for r in alerts]


def test_dismissed_and_snooze_expired_reappears(db, make_user):
    owner = make_user()
    approver = make_user(role=Role.approver)
    now = datetime(2026, 1, 10)
    report = make_report(db, owner, submitted_at=now - timedelta(days=5))
    stale_alerts.dismiss(db, report, approver, now=now)  # snoozes for stale_alert_snooze_days

    later = now + timedelta(days=999)  # well past any snooze window
    alerts = stale_alerts.get_alerts_for_approver(db, approver, now=later)
    assert report.id in [r.id for r in alerts]


def test_report_leaving_submitted_drops_out_immediately(db, make_user):
    owner = make_user()
    approver = make_user(role=Role.approver)
    now = datetime(2026, 1, 10)
    report = make_report(db, owner, submitted_at=now - timedelta(days=10))
    assert report.id in [r.id for r in stale_alerts.get_alerts_for_approver(db, approver, now=now)]

    report.status = ReportStatus.approved
    db.flush()
    assert report.id not in [r.id for r in stale_alerts.get_alerts_for_approver(db, approver, now=now)]


def test_dismissal_is_per_approver_not_global(db, make_user):
    owner = make_user()
    dave = make_user(role=Role.approver)
    carol = make_user(role=Role.approver)
    now = datetime(2026, 1, 10)
    report = make_report(db, owner, submitted_at=now - timedelta(days=5))
    stale_alerts.dismiss(db, report, dave, now=now)

    # Dave dismissed it - gone from his list...
    assert report.id not in [r.id for r in stale_alerts.get_alerts_for_approver(db, dave, now=now)]
    # ...but Carol never dismissed it, so it's still in hers.
    assert report.id in [r.id for r in stale_alerts.get_alerts_for_approver(db, carol, now=now)]


def test_redismiss_resets_snooze(db, make_user):
    owner = make_user()
    approver = make_user(role=Role.approver)
    now = datetime(2026, 1, 10)
    report = make_report(db, owner, submitted_at=now - timedelta(days=5))
    stale_alerts.dismiss(db, report, approver, now=now)

    later = now + timedelta(days=999)
    assert report.id in [r.id for r in stale_alerts.get_alerts_for_approver(db, approver, now=later)]

    stale_alerts.dismiss(db, report, approver, now=later)  # dismiss again
    assert report.id not in [
        r.id for r in stale_alerts.get_alerts_for_approver(db, approver, now=later + timedelta(hours=1))
    ]


# --- API level ---


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


def test_alerts_endpoint_and_dismiss(client, make_user, db):
    alice = make_user()
    carol = make_user(role=Role.approver)
    report = make_report(db, alice, submitted_at=datetime.utcnow() - timedelta(days=10))
    db.commit()

    r = client.get("/alerts", headers=auth_headers(carol))
    assert r.status_code == 200
    assert any(item["id"] == report.id for item in r.json())

    r = client.post(f"/alerts/{report.id}/dismiss", headers=auth_headers(carol))
    assert r.status_code == 200

    r = client.get("/alerts", headers=auth_headers(carol))
    assert all(item["id"] != report.id for item in r.json())


def test_alerts_requires_approver_role(client, make_user):
    alice = make_user()
    r = client.get("/alerts", headers=auth_headers(alice))
    assert r.status_code == 403
