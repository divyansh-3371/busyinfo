r"""The lifecycle/authorization rules for expense reports, centralized here so every
route (single-decide, bulk-decide, tests) goes through the same logic instead of each
re-implementing the transition table and the self-approval check.

Draft -> Submitted -> Approved -> Paid
                   \-> Rejected -> Draft (automatic, same action)
"""
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy.orm import Session

from app.models.enums import ReportStatus, Role
from app.models.line import ExpenseLine
from app.models.report import ExpenseReport
from app.models.status_event import StatusEvent
from app.models.user import User


class DomainError(Exception):
    """Raised for any illegal transition or rule violation. The message is meant to be
    shown to the end user as-is, per the brief's "rejected by the server with a message
    explaining why"."""


class SelfApprovalError(DomainError):
    """Specifically: an approver tried to act on a report they own. Its own subclass
    so bulk-decide can identify this exact reason instead of pattern-matching text."""


def recalculate_total(report: ExpenseReport, db: Session) -> None:
    """The report's total is always the sum of its lines' amounts, computed here -
    never trust a client-sent total. Called after every line add/edit/remove."""
    total = (
        db.query(ExpenseLine)
        .filter(ExpenseLine.report_id == report.id)
        .with_entities(ExpenseLine.amount_cents)
        .all()
    )
    report.total_cents = sum(amount for (amount,) in total)


def _log_event(
    db: Session,
    report: ExpenseReport,
    *,
    from_status: ReportStatus | None,
    to_status: ReportStatus,
    actor: User,
    reason: str | None = None,
) -> None:
    db.add(
        StatusEvent(
            report_id=report.id,
            from_status=from_status,
            to_status=to_status,
            actor_id=actor.id,
            reason=reason,
        )
    )


def submit(db: Session, report: ExpenseReport, actor: User) -> None:
    if actor.id != report.owner_id:
        raise DomainError("Only the report's owner can submit it.")
    if report.status != ReportStatus.draft:
        raise DomainError(f"Cannot submit a report that is currently {report.status.value}.")
    _log_event(db, report, from_status=report.status, to_status=ReportStatus.submitted, actor=actor)
    report.status = ReportStatus.submitted
    report.submitted_at = datetime.now(timezone.utc)


def decide(
    db: Session,
    report: ExpenseReport,
    actor: User,
    decision: Literal["approved", "rejected"],
    reason: str | None = None,
) -> None:
    if actor.role != Role.approver:
        raise DomainError("Only an approver can decide on a report.")
    if actor.id == report.owner_id:
        raise SelfApprovalError("An approver cannot decide on their own report.")
    if report.status != ReportStatus.submitted:
        raise DomainError(f"Cannot decide on a report that is currently {report.status.value}.")

    if decision == "rejected":
        if not reason or not reason.strip():
            raise DomainError("Rejecting a report requires a reason.")
        _log_event(
            db, report, from_status=report.status, to_status=ReportStatus.rejected,
            actor=actor, reason=reason,
        )
        # Automatic follow-on, same action: a rejected report always returns to Draft
        # immediately so its owner can edit and resubmit.
        _log_event(db, report, from_status=ReportStatus.rejected, to_status=ReportStatus.draft, actor=actor)
        report.status = ReportStatus.draft
    else:
        _log_event(
            db, report, from_status=report.status, to_status=ReportStatus.approved, actor=actor
        )
        report.status = ReportStatus.approved


def mark_paid(db: Session, report: ExpenseReport, actor: User) -> None:
    if actor.role != Role.approver:
        raise DomainError("Only an approver can mark a report as paid.")
    if actor.id == report.owner_id:
        raise SelfApprovalError("An approver cannot mark their own report as paid.")
    if report.status != ReportStatus.approved:
        raise DomainError(f"Cannot mark as paid a report that is currently {report.status.value}.")
    _log_event(db, report, from_status=report.status, to_status=ReportStatus.paid, actor=actor)
    report.status = ReportStatus.paid


def archive(report: ExpenseReport) -> None:
    if report.archived_at is not None:
        raise DomainError("Report is already archived.")
    report.archived_at = datetime.now(timezone.utc)


def restore(report: ExpenseReport) -> None:
    if report.archived_at is None:
        raise DomainError("Report is not archived.")
    report.archived_at = None
