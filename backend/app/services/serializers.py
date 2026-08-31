"""Shared model -> response-schema conversions, so routes that both need the full
report representation (reports.py, decisions.py, and later bulk-decide) don't
duplicate it or import from each other."""
from app.models.report import ExpenseReport
from app.schemas.report import ReportDetail


def to_report_detail(report: ExpenseReport) -> ReportDetail:
    return ReportDetail(
        id=report.id,
        title=report.title,
        owner=report.owner,
        status=report.status,
        total_cents=report.total_cents,
        start_date=report.start_date,
        end_date=report.end_date,
        submitted_at=report.submitted_at,
        archived_at=report.archived_at,
        created_at=report.created_at,
        lines=report.lines,
        approvers=[link.approver for link in report.approver_links],
        status_events=report.status_events,
        comments=report.comments,
    )
