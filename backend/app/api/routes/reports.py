import csv
import io
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_visible_report, require_approver
from app.db.session import get_db
from app.models.approver import ReportApprover
from app.models.enums import ReportStatus, Role
from app.models.report import ExpenseReport
from app.models.user import User
from app.schemas.report import (
    AssignApproversRequest,
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

    if not include_archived:
        query = query.filter(ExpenseReport.archived_at.is_(None))

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
def list_approvers(db: Session = Depends(get_db), _: User = Depends(require_approver)) -> list[User]:
    """All users with the approver role - used to populate the assignment picker."""
    return db.query(User).filter(User.role == Role.approver).order_by(User.name).all()


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
                r.title,
                r.owner.name,
                r.owner.email,
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
def get_report(report: ExpenseReport = Depends(get_visible_report)) -> ReportDetail:
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
    _: User = Depends(require_approver),
) -> ReportDetail:
    """Replaces the full set of assigned approvers. Any approver may manage
    assignments on any report they can see - assignment is a queue-filtering
    convenience, not an access gate (see docs/decisions.md), so this isn't restricted
    to the report's owner."""
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
