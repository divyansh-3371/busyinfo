"""Dashboard aggregates (goal 8). Scoped like everything else in this app: an
approver sees company-wide numbers, an employee sees numbers for their own reports
only - there's no reason the dashboard should be the one place that breaks the
"employees see only their own" rule used everywhere else.

"This week" is a trailing 7-day window ending at `now`, not a calendar week - simpler
to reason about and to test with a fixed `now`, and avoids a Monday-vs-Sunday
argument. Same convention for the 8-week paid-per-week series.
"""
from datetime import datetime, timedelta

from sqlalchemy import func, true
from sqlalchemy.orm import Session

from app.models.enums import ExpenseCategory, ReportStatus, Role
from app.models.line import ExpenseLine
from app.models.report import ExpenseReport
from app.models.status_event import StatusEvent
from app.models.user import User

WEEKS_OF_HISTORY = 8


def compute_dashboard(db: Session, user: User, *, now: datetime | None = None) -> dict:
    now = now or datetime.utcnow()
    week_start = now - timedelta(days=7)
    scope_filter = true() if user.role == Role.approver else (ExpenseReport.owner_id == user.id)

    reports_q = db.query(ExpenseReport).filter(scope_filter)

    awaiting_approval_count = reports_q.filter(ExpenseReport.status == ReportStatus.submitted).count()

    total_due_cents = (
        reports_q.filter(ExpenseReport.status == ReportStatus.approved)
        .with_entities(func.coalesce(func.sum(ExpenseReport.total_cents), 0))
        .scalar()
    )

    status_rows = (
        db.query(ExpenseReport.status, func.count(ExpenseReport.id))
        .filter(scope_filter)
        .group_by(ExpenseReport.status)
        .all()
    )
    status_breakdown = {s.value: 0 for s in ReportStatus}
    for status_value, count in status_rows:
        status_breakdown[status_value.value] = count

    category_rows = (
        db.query(ExpenseLine.category, func.coalesce(func.sum(ExpenseLine.amount_cents), 0))
        .join(ExpenseReport, ExpenseLine.report_id == ExpenseReport.id)
        .filter(scope_filter)
        .group_by(ExpenseLine.category)
        .all()
    )
    category_breakdown = {c.value: 0 for c in ExpenseCategory}
    for category_value, total in category_rows:
        category_breakdown[category_value.value] = total

    def _event_count_this_week(to_status: ReportStatus) -> int:
        return (
            db.query(StatusEvent)
            .join(ExpenseReport, StatusEvent.report_id == ExpenseReport.id)
            .filter(scope_filter)
            .filter(StatusEvent.to_status == to_status)
            .filter(StatusEvent.created_at >= week_start)
            .count()
        )

    approved_this_week_count = _event_count_this_week(ReportStatus.approved)
    paid_this_week_count = _event_count_this_week(ReportStatus.paid)

    paid_per_week = []
    for i in range(WEEKS_OF_HISTORY):
        bucket_end = now - timedelta(days=7 * i)
        bucket_start = bucket_end - timedelta(days=7)
        total = (
            db.query(func.coalesce(func.sum(ExpenseReport.total_cents), 0))
            .join(StatusEvent, StatusEvent.report_id == ExpenseReport.id)
            .filter(scope_filter)
            .filter(StatusEvent.to_status == ReportStatus.paid)
            .filter(StatusEvent.created_at >= bucket_start, StatusEvent.created_at < bucket_end)
            .scalar()
        )
        paid_per_week.append(
            {"week_start": bucket_start.date(), "week_end": bucket_end.date(), "total_cents": total}
        )
    paid_per_week.reverse()  # oldest first, for charting left-to-right

    return {
        "awaiting_approval_count": awaiting_approval_count,
        "total_due_cents": total_due_cents,
        "approved_this_week_count": approved_this_week_count,
        "paid_this_week_count": paid_this_week_count,
        "status_breakdown": status_breakdown,
        "category_breakdown": category_breakdown,
        "paid_per_week": paid_per_week,
    }
