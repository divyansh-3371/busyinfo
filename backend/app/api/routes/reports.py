import csv
import io
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_visible_report, require_approver
from app.db.session import get_db
from app.models.approver import ReportApprover
from app.models.enums import ReportStatus, Role
from app.models.report import ExpenseReport
from app.models.user import User
from app.schemas.report import (
    AssignApproversRequest,
    NeedsAttentionCount,
    ReportCreate,
    ReportDetail,
    ReportListResponse,
    ReportUpdate,
)
from app.schemas.user import UserOut
from app.services.report_rules import DomainError, archive, restore
from app.services.serializers import to_report_detail as _to_detail

router = APIRouter(prefix="/reports", tags=["reports"])

SortField = Literal["created_at", "submitted_at", "status", "total_cents"]
SORT_COLUMNS = {
    "created_at": ExpenseReport.created_at,
    "submitted_at": ExpenseReport.submitted_at,
    "status": ExpenseReport.status,
    "total_cents": ExpenseReport.total_cents,
}


@router.get("", response_model=ReportListResponse)
def list_reports(
    q: str | None = None,
    status_filter: ReportStatus | None = Query(None, alias="status"),
    owner_id: int | None = None,
    approver_id: int | None = None,
    assigned_to_me: bool = False,
    include_archived: bool = False,
    sort: SortField = "created_at",
    sort_dir: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReportListResponse:
    """Everything server-side: text search, status/owner/approver filters, sort, and
    pagination with a total count - never fetch-everything-then-filter-in-Python."""
    query = db.query(ExpenseReport)

    if user.role != Role.approver:
        query = query.filter(ExpenseReport.owner_id == user.id)
    else:
        # Approvers see everything submitted-or-later, plus their own reports
        # regardless of status - a Draft is another employee's private, unfinished
        # work and isn't visible to anyone else until they submit it (matches the
        # same rule in get_visible_report).
        query = query.filter(
            or_(ExpenseReport.owner_id == user.id, ExpenseReport.status != ReportStatus.draft)
        )

    if not include_archived:
        query = query.filter(ExpenseReport.archived_at.is_(None))

    q = q.strip() if q else q
    if q:
        query = query.filter(ExpenseReport.title.ilike(f"%{q}%"))

    if status_filter is not None:
        query = query.filter(ExpenseReport.status == status_filter)

    if owner_id is not None:
        query = query.filter(ExpenseReport.owner_id == owner_id)

    effective_approver_id = approver_id
    if assigned_to_me and user.role == Role.approver:
        effective_approver_id = user.id
    if effective_approver_id is not None:
        query = query.filter(
            ExpenseReport.approver_links.any(ReportApprover.approver_id == effective_approver_id)
        )

    total = query.count()

    column = SORT_COLUMNS[sort]
    order = column.asc() if sort_dir == "asc" else column.desc()
    if sort == "submitted_at":
        order = order.nulls_last()
    query = query.order_by(order)

    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return ReportListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/approvers", response_model=list[UserOut])
def list_approvers(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> list[User]:
    """All users with the approver role - used to populate the assignment picker.
    Open to any authenticated user (not just approvers) now that a report's owner
    can also manage its assignments - just names/emails of who the approvers are,
    nothing sensitive."""
    return db.query(User).filter(User.role == Role.approver).order_by(User.name).all()


@router.get("/needs-attention-count", response_model=NeedsAttentionCount)
def needs_attention_count(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> NeedsAttentionCount:
    """How many of *my own* reports still have an unacknowledged rejection - the
    nav badge that tells you a rejection needs your attention, since nothing else
    does (no email, no push notification - this app sends none). Applies to
    anyone who owns a report, not just employees: an approver can just as easily
    have their own report rejected by someone else. Clears per-report the moment
    you view it (GET /reports/{id}) or resubmit it - see
    ExpenseReport.needs_owner_attention."""
    count = (
        db.query(ExpenseReport)
        .filter(ExpenseReport.owner_id == user.id, ExpenseReport.needs_owner_attention.is_(True))
        .count()
    )
    return NeedsAttentionCount(count=count)


_FORMULA_TRIGGER_CHARS = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value: str) -> str:
    """Neutralizes spreadsheet formula injection (CSV/Formula Injection, CWE-1236):
    Excel and Google Sheets treat a cell starting with =, +, -, or @ as a formula
    to evaluate when the file is opened, not literal text. `title` is set by any
    employee with no character restrictions and flows straight into this export -
    which exists specifically to be opened in a spreadsheet by an approver/finance
    user. A leading apostrophe is the standard spreadsheet convention forcing the
    cell to render as plain text instead of being evaluated."""
    if value and value[0] in _FORMULA_TRIGGER_CHARS:
        return "'" + value
    return value


@router.get("/export-due")
def export_due(db: Session = Depends(get_db), _: User = Depends(require_approver)) -> StreamingResponse:
    """CSV of every Approved-but-unpaid report - the reimbursements due (goal 7).
    Registered before the dynamic GET /{report_id} route (same reason as /approvers
    above): a literal path segment must be matched before a path parameter would
    otherwise shadow it."""
    reports = (
        db.query(ExpenseReport)
        .filter(ExpenseReport.status == ReportStatus.approved)
        .order_by(ExpenseReport.submitted_at)
        .all()
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["report_id", "title", "owner_name", "owner_email", "total_usd", "start_date", "end_date", "submitted_at"]
    )
    for r in reports:
        writer.writerow(
            [
                r.id,
                _csv_safe(r.title),
                _csv_safe(r.owner.name),
                _csv_safe(r.owner.email),
                f"{r.total_cents / 100:.2f}",
                r.start_date.isoformat(),
                r.end_date.isoformat(),
                r.submitted_at.isoformat() if r.submitted_at else "",
            ]
        )
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=reimbursements_due.csv"},
    )


@router.post("", response_model=ReportDetail, status_code=status.HTTP_201_CREATED)
def create_report(
    payload: ReportCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> ReportDetail:
    report = ExpenseReport(
        owner_id=user.id,
        title=payload.title,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status=ReportStatus.draft,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return _to_detail(report)


@router.get("/{report_id}", response_model=ReportDetail)
def get_report(
    report: ExpenseReport = Depends(get_visible_report),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReportDetail:
    # Viewing it is what "interacting with it" means for clearing the rejected
    # mark - the owner opening the report is itself the acknowledgment, no
    # separate "mark as read" click needed. Scoped to the owner specifically:
    # an approver opening the same report (they're allowed to, once it's
    # visible to them) shouldn't clear a mark that isn't about them.
    if report.owner_id == user.id and report.needs_owner_attention:
        report.needs_owner_attention = False
        db.commit()
        db.refresh(report)
    return _to_detail(report)


@router.patch("/{report_id}", response_model=ReportDetail)
def update_report(
    payload: ReportUpdate,
    report: ExpenseReport = Depends(get_visible_report),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReportDetail:
    if report.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the report's owner can edit it.")
    if report.status != ReportStatus.draft:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Cannot edit a report that is currently {report.status.value}.",
        )
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(report, field, value)
    if report.end_date < report.start_date:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "End date cannot be before start date.")
    db.commit()
    db.refresh(report)
    return _to_detail(report)


@router.post("/{report_id}/archive", response_model=ReportDetail)
def archive_report(
    report: ExpenseReport = Depends(get_visible_report),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReportDetail:
    if report.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the report's owner can archive it.")
    try:
        archive(report)
    except DomainError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    db.commit()
    db.refresh(report)
    return _to_detail(report)


@router.post("/{report_id}/restore", response_model=ReportDetail)
def restore_report(
    report: ExpenseReport = Depends(get_visible_report),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReportDetail:
    if report.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the report's owner can restore it.")
    try:
        restore(report)
    except DomainError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    db.commit()
    db.refresh(report)
    return _to_detail(report)


@router.put("/{report_id}/approvers", response_model=ReportDetail)
def set_approvers(
    payload: AssignApproversRequest,
    report: ExpenseReport = Depends(get_visible_report),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReportDetail:
    """Replaces the full set of assigned approvers. Any approver may manage
    assignments on any report they can see (assignment is a queue-filtering
    convenience, not an access gate - see docs/decisions.md), and so can the
    report's own owner, even if they're not an approver themselves - being able to
    route your own report to whoever should be reviewing it is a reasonable thing
    to want, and it can't be misused as a backdoor around self-approval: assignment
    grants no actual power, decide()/mark_paid() re-check ownership independently
    regardless of who's assigned. A plain employee who neither owns the report nor
    holds the approver role still can't touch this."""
    if user.role != Role.approver and user.id != report.owner_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only an approver or the report's own owner can manage its assignments.",
        )
    unique_ids = set(payload.approver_ids)
    if unique_ids:
        found = (
            db.query(User.id)
            .filter(User.id.in_(unique_ids), User.role == Role.approver)
            .all()
        )
        found_ids = {uid for (uid,) in found}
        missing = unique_ids - found_ids
        if missing:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Not valid approver user ids: {sorted(missing)}",
            )

    db.query(ReportApprover).filter(ReportApprover.report_id == report.id).delete()
    for approver_id in unique_ids:
        db.add(ReportApprover(report_id=report.id, approver_id=approver_id))
    db.commit()
    db.refresh(report)
    return _to_detail(report)
