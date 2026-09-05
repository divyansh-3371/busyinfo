from datetime import date

import pytest

from app.models.enums import ExpenseCategory, ReportStatus, Role
from app.models.line import ExpenseLine
from app.models.report import ExpenseReport
from app.services import report_rules
from app.services.report_rules import DomainError, SelfApprovalError


def make_report(db, owner, status=ReportStatus.draft) -> ExpenseReport:
    report = ExpenseReport(
        owner_id=owner.id,
        title="Test report",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 2),
        status=status,
    )
    db.add(report)
    db.flush()
    return report


# --- submit ---


def test_submit_by_owner_succeeds(db, make_user):
    owner = make_user()
    report = make_report(db, owner)
    report_rules.submit(db, report, owner)
    assert report.status == ReportStatus.submitted


def test_submit_by_non_owner_rejected(db, make_user):
    owner = make_user()
    other = make_user()
    report = make_report(db, owner)
    with pytest.raises(DomainError):
        report_rules.submit(db, report, other)
    assert report.status == ReportStatus.draft


def test_submit_non_draft_rejected(db, make_user):
    owner = make_user()
    report = make_report(db, owner, status=ReportStatus.submitted)
    with pytest.raises(DomainError):
        report_rules.submit(db, report, owner)


# --- decide ---


def test_approve_by_non_owning_approver_succeeds(db, make_user):
    owner = make_user()
    approver = make_user(role=Role.approver)
    report = make_report(db, owner, status=ReportStatus.submitted)
    report_rules.decide(db, report, approver, "approved")
    assert report.status == ReportStatus.approved


def test_approve_by_employee_rejected(db, make_user):
    owner = make_user()
    employee = make_user()
    report = make_report(db, owner, status=ReportStatus.submitted)
    with pytest.raises(DomainError):
        report_rules.decide(db, report, employee, "approved")


def test_self_approval_blocked_even_though_actor_is_an_approver(db, make_user):
    """The specific rule the brief spells out: an approver can never decide on their
    own report, even though they hold the role."""
    owner_approver = make_user(role=Role.approver)
    report = make_report(db, owner_approver, status=ReportStatus.submitted)
    with pytest.raises(SelfApprovalError):
        report_rules.decide(db, report, owner_approver, "approved")
    assert report.status == ReportStatus.submitted  # unchanged


def test_reject_requires_a_reason(db, make_user):
    owner = make_user()
    approver = make_user(role=Role.approver)
    report = make_report(db, owner, status=ReportStatus.submitted)
    with pytest.raises(DomainError):
        report_rules.decide(db, report, approver, "rejected", reason=None)
    with pytest.raises(DomainError):
        report_rules.decide(db, report, approver, "rejected", reason="   ")


def test_reject_returns_report_to_draft_and_logs_both_transitions(db, make_user):
    owner = make_user()
    approver = make_user(role=Role.approver)
    report = make_report(db, owner, status=ReportStatus.submitted)
    report_rules.decide(db, report, approver, "rejected", reason="Missing receipt")
    assert report.status == ReportStatus.draft

    events = sorted(report.status_events, key=lambda e: e.id)
    assert len(events) == 2
    assert (events[0].from_status, events[0].to_status) == (
        ReportStatus.submitted,
        ReportStatus.rejected,
    )
    assert events[0].reason == "Missing receipt"
    assert (events[1].from_status, events[1].to_status) == (
        ReportStatus.rejected,
        ReportStatus.draft,
    )


def test_reject_snapshots_lines_and_the_snapshot_survives_later_edits(db, make_user):
    """The whole point of the snapshot: what the approver actually saw at rejection
    time must stay exactly that, even after the owner edits the line and resubmits."""
    owner = make_user()
    approver = make_user(role=Role.approver)
    report = make_report(db, owner, status=ReportStatus.submitted)
    line = ExpenseLine(
        report_id=report.id, date=date(2026, 1, 1), category=ExpenseCategory.travel,
        amount_cents=1000, description="Cab",
    )
    db.add(line)
    db.flush()

    report_rules.decide(db, report, approver, "rejected", reason="Missing receipt")

    reject_event = next(e for e in report.status_events if e.to_status == ReportStatus.rejected)
    draft_event = next(e for e in report.status_events if e.to_status == ReportStatus.draft)
    assert reject_event.line_snapshot == [
        {
            "date": "2026-01-01",
            "category": "travel",
            "amount_cents": 1000,
            "description": "Cab",
            "other_category_note": None,
        }
    ]
    # The mechanical rejected->draft follow-on isn't a new decision - no snapshot.
    assert draft_event.line_snapshot is None

    # Owner edits the line after the rejection - the frozen snapshot must not move.
    line.amount_cents = 9999
    line.description = "Changed after the fact"
    db.flush()
    assert reject_event.line_snapshot[0]["amount_cents"] == 1000
    assert reject_event.line_snapshot[0]["description"] == "Cab"


def test_approve_also_snapshots_lines(db, make_user):
    """Symmetric with rejection, for consistency - even though an approved
    report's lines can never be edited again anyway."""
    owner = make_user()
    approver = make_user(role=Role.approver)
    report = make_report(db, owner, status=ReportStatus.submitted)
    db.add(
        ExpenseLine(
            report_id=report.id, date=date(2026, 1, 1), category=ExpenseCategory.meals,
            amount_cents=500, description="Lunch",
        )
    )
    db.flush()

    report_rules.decide(db, report, approver, "approved")

    approve_event = next(e for e in report.status_events if e.to_status == ReportStatus.approved)
    assert approve_event.line_snapshot == [
        {
            "date": "2026-01-01",
            "category": "meals",
            "amount_cents": 500,
            "description": "Lunch",
            "other_category_note": None,
        }
    ]


def test_decide_on_non_submitted_report_rejected(db, make_user):
    owner = make_user()
    approver = make_user(role=Role.approver)
    report = make_report(db, owner, status=ReportStatus.draft)
    with pytest.raises(DomainError):
        report_rules.decide(db, report, approver, "approved")


def test_illegal_transitions_write_no_status_event(db, make_user):
    """PLAN.md's edge-case list: 'Illegal transition attempts do not write a
    StatusEvent - only real transitions do.' True by construction (every guard in
    report_rules.py raises before the StatusEvent append), but that ordering has
    nothing else enforcing it - a refactor could silently reverse it. Cover every
    rejection path from this file that's tested for status alone, and also check
    the audit trail actually stayed empty."""
    owner = make_user()
    other = make_user()
    employee = make_user()
    approver = make_user(role=Role.approver)
    owner_approver = make_user(role=Role.approver)

    draft_report = make_report(db, owner)
    with pytest.raises(DomainError):
        report_rules.submit(db, draft_report, other)  # non-owner submit
    assert len(draft_report.status_events) == 0

    submitted_report = make_report(db, owner, status=ReportStatus.submitted)
    with pytest.raises(DomainError):
        report_rules.decide(db, submitted_report, employee, "approved")  # non-approver
    with pytest.raises(DomainError):
        report_rules.decide(db, submitted_report, approver, "rejected", reason=None)  # no reason
    assert len(submitted_report.status_events) == 0

    self_owned_report = make_report(db, owner_approver, status=ReportStatus.submitted)
    with pytest.raises(SelfApprovalError):
        report_rules.decide(db, self_owned_report, owner_approver, "approved")
    assert len(self_owned_report.status_events) == 0

    draft_again = make_report(db, owner)
    with pytest.raises(DomainError):
        report_rules.mark_paid(db, draft_again, approver)  # not approved yet
    assert len(draft_again.status_events) == 0


# --- mark_paid ---


def test_mark_paid_by_non_owning_approver_succeeds(db, make_user):
    owner = make_user()
    approver = make_user(role=Role.approver)
    report = make_report(db, owner, status=ReportStatus.approved)
    report_rules.mark_paid(db, report, approver)
    assert report.status == ReportStatus.paid


def test_mark_paid_self_owned_blocked(db, make_user):
    owner_approver = make_user(role=Role.approver)
    report = make_report(db, owner_approver, status=ReportStatus.approved)
    with pytest.raises(SelfApprovalError):
        report_rules.mark_paid(db, report, owner_approver)


def test_mark_paid_non_approved_rejected(db, make_user):
    owner = make_user()
    approver = make_user(role=Role.approver)
    report = make_report(db, owner, status=ReportStatus.submitted)
    with pytest.raises(DomainError):
        report_rules.mark_paid(db, report, approver)


# --- recalculate_total ---


def test_recalculate_total_sums_lines(db, make_user):
    owner = make_user()
    report = make_report(db, owner)
    db.add_all(
        [
            ExpenseLine(
                report_id=report.id,
                date=date(2026, 1, 1),
                amount_cents=1000,
                category=ExpenseCategory.travel,
                description="a",
            ),
            ExpenseLine(
                report_id=report.id,
                date=date(2026, 1, 1),
                amount_cents=2500,
                category=ExpenseCategory.meals,
                description="b",
            ),
        ]
    )
    db.flush()
    report_rules.recalculate_total(report, db)
    assert report.total_cents == 3500


def test_recalculate_total_zero_lines(db, make_user):
    owner = make_user()
    report = make_report(db, owner)
    report_rules.recalculate_total(report, db)
    assert report.total_cents == 0


# --- archive/restore ---


def test_archive_then_restore(db, make_user):
    owner = make_user()
    report = make_report(db, owner)
    report_rules.archive(report)
    assert report.archived_at is not None
    report_rules.restore(report)
    assert report.archived_at is None


def test_double_archive_rejected(db, make_user):
    owner = make_user()
    report = make_report(db, owner)
    report_rules.archive(report)
    with pytest.raises(DomainError):
        report_rules.archive(report)


def test_restore_non_archived_rejected(db, make_user):
    owner = make_user()
    report = make_report(db, owner)
    with pytest.raises(DomainError):
        report_rules.restore(report)
