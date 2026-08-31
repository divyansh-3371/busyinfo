"""Stale-approval alerts (goal 10).

Interpretation choice, documented here since this is one of the brief's explicitly
called-out exact rules: the alerts list is global (every stale Submitted report,
matching the "approvers see everything" pattern used everywhere else in this app),
and dismissal is per-approver, personal state - one approver dismissing an alert does
not hide it from other approvers, and any approver may dismiss any stale report's
alert (not restricted to reports assigned to them). This keeps assignment consistent
with its role everywhere else in this system: a queue-filter convenience, never an
access gate (see docs/decisions.md) - and avoids a report with zero assigned
approvers being an alert nobody can ever dismiss.

All timestamps here are naive UTC, matching how they're actually stored: Postgres
TIMESTAMP WITHOUT TIME ZONE strips tzinfo from whatever's written, so comparing a
timezone-aware "now" against a value read back from the DB raises TypeError.
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.alert import AlertDismissal
from app.models.enums import ReportStatus
from app.models.report import ExpenseReport
from app.models.user import User

settings = get_settings()


def now_utc() -> datetime:
    return datetime.utcnow()


def is_stale(report: ExpenseReport, *, now: datetime | None = None, stale_days: int | None = None) -> bool:
    if report.status != ReportStatus.submitted or report.submitted_at is None:
        return False
    now = now or now_utc()
    stale_days = settings.stale_alert_days if stale_days is None else stale_days
    return (now - report.submitted_at) >= timedelta(days=stale_days)


def get_alerts_for_approver(
    db: Session, approver: User, *, now: datetime | None = None
) -> list[ExpenseReport]:
    """Every stale report, excluding ones this specific approver has an
    active (non-expired) dismissal for."""
    now = now or now_utc()
    candidates = (
        db.query(ExpenseReport)
        .filter(ExpenseReport.status == ReportStatus.submitted)
        .filter(ExpenseReport.submitted_at.isnot(None))
        .all()
    )
    stale = [r for r in candidates if is_stale(r, now=now)]
    if not stale:
        return []

    report_ids = [r.id for r in stale]
    dismissals = {
        d.report_id: d
        for d in db.query(AlertDismissal)
        .filter(
            AlertDismissal.report_id.in_(report_ids),
            AlertDismissal.approver_id == approver.id,
        )
        .all()
    }
    return [r for r in stale if r.id not in dismissals or dismissals[r.id].snoozed_until <= now]


def dismiss(db: Session, report: ExpenseReport, approver: User, *, now: datetime | None = None) -> None:
    """Upsert: dismissing again (e.g. after the alert reappeared) resets the snooze
    rather than erroring or accumulating rows - see NOTES.md."""
    now = now or now_utc()
    snoozed_until = now + timedelta(days=settings.stale_alert_snooze_days)
    existing = (
        db.query(AlertDismissal)
        .filter(AlertDismissal.report_id == report.id, AlertDismissal.approver_id == approver.id)
        .first()
    )
    if existing:
        existing.dismissed_at = now
        existing.snoozed_until = snoozed_until
    else:
        db.add(
            AlertDismissal(
                report_id=report.id,
                approver_id=approver.id,
                dismissed_at=now,
                snoozed_until=snoozed_until,
            )
        )
