from datetime import date, datetime, timedelta

from app.models.enums import ExpenseCategory, ReportStatus, Role
from app.models.line import ExpenseLine
from app.models.report import ExpenseReport
from app.models.status_event import StatusEvent
from app.services.dashboard import compute_dashboard

NOW = datetime(2026, 6, 15, 12, 0, 0)


def make_report(db, owner, status, *, total_cents=0, lines=()):
    report = ExpenseReport(
        owner_id=owner.id,
        title="Report",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 2),
        status=status,
        total_cents=total_cents,
    )
    db.add(report)
    db.flush()
    for category, amount in lines:
        db.add(
            ExpenseLine(
                report_id=report.id,
                date=date(2026, 1, 1),
                amount_cents=amount,
                category=category,
                description="x",
            )
        )
    db.flush()
    return report


def add_event(db, report, to_status, actor, created_at):
    db.add(
        StatusEvent(
            report_id=report.id,
            from_status=None,
            to_status=to_status,
            actor_id=actor.id,
            created_at=created_at,
        )
    )


def test_awaiting_approval_and_total_due(db, make_user):
    alice = make_user()
    carol = make_user(role=Role.approver)
    make_report(db, alice, ReportStatus.submitted, total_cents=1000)
    make_report(db, alice, ReportStatus.approved, total_cents=2500)
    make_report(db, alice, ReportStatus.approved, total_cents=1500)
    db.flush()

    result = compute_dashboard(db, carol, now=NOW)
    assert result["awaiting_approval_count"] == 1
    assert result["total_due_cents"] == 4000


def test_status_breakdown_includes_zero_statuses(db, make_user):
    carol = make_user(role=Role.approver)
    result = compute_dashboard(db, carol, now=NOW)
    assert result["status_breakdown"] == {
        "draft": 0, "submitted": 0, "approved": 0, "rejected": 0, "paid": 0,
    }


def test_category_breakdown_sums_lines(db, make_user):
    alice = make_user()
    carol = make_user(role=Role.approver)
    make_report(
        db, alice, ReportStatus.draft,
        lines=[(ExpenseCategory.travel, 1000), (ExpenseCategory.travel, 500), (ExpenseCategory.meals, 300)],
    )
    result = compute_dashboard(db, carol, now=NOW)
    assert result["category_breakdown"]["travel"] == 1500
    assert result["category_breakdown"]["meals"] == 300
    assert result["category_breakdown"]["software"] == 0


def test_approved_and_paid_this_week(db, make_user):
    alice = make_user()
    carol = make_user(role=Role.approver)
    report = make_report(db, alice, ReportStatus.paid, total_cents=5000)
    add_event(db, report, ReportStatus.approved, carol, NOW - timedelta(days=3))
    add_event(db, report, ReportStatus.paid, carol, NOW - timedelta(days=1))

    old_report = make_report(db, alice, ReportStatus.paid, total_cents=9000)
    add_event(db, old_report, ReportStatus.approved, carol, NOW - timedelta(days=20))
    add_event(db, old_report, ReportStatus.paid, carol, NOW - timedelta(days=19))
    db.flush()

    result = compute_dashboard(db, carol, now=NOW)
    assert result["approved_this_week_count"] == 1
    assert result["paid_this_week_count"] == 1


def test_paid_per_week_series_has_eight_buckets_oldest_first(db, make_user):
    alice = make_user()
    carol = make_user(role=Role.approver)
    recent = make_report(db, alice, ReportStatus.paid, total_cents=1000)
    add_event(db, recent, ReportStatus.paid, carol, NOW - timedelta(days=2))

    eight_weeks_ago = make_report(db, alice, ReportStatus.paid, total_cents=2000)
    add_event(db, eight_weeks_ago, ReportStatus.paid, carol, NOW - timedelta(days=51))
    db.flush()

    result = compute_dashboard(db, carol, now=NOW)
    series = result["paid_per_week"]
    assert len(series) == 8
    assert series[-1]["total_cents"] == 1000  # most recent bucket, last in the list
    assert series[0]["week_start"] < series[-1]["week_start"]  # oldest first
    assert sum(bucket["total_cents"] for bucket in series) == 3000


def test_employee_scoped_to_own_reports(db, make_user):
    alice = make_user()
    bob = make_user()
    make_report(db, alice, ReportStatus.submitted, total_cents=1000)
    make_report(db, bob, ReportStatus.submitted, total_cents=2000)

    result = compute_dashboard(db, alice, now=NOW)
    assert result["awaiting_approval_count"] == 1  # only Alice's own

    result = compute_dashboard(db, bob, now=NOW)
    assert result["awaiting_approval_count"] == 1  # only Bob's own
