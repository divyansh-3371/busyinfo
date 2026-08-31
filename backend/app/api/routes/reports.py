from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_visible_report
from app.db.session import get_db
from app.models.enums import ReportStatus, Role
from app.models.report import ExpenseReport
from app.models.user import User
from app.schemas.report import ReportCreate, ReportDetail, ReportListItem, ReportUpdate
from app.services.report_rules import DomainError, archive, restore
from app.services.serializers import to_report_detail as _to_detail

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("", response_model=list[ReportListItem])
def list_reports(
    include_archived: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ExpenseReport]:
    """Basic version for now: everything the user can see, newest first, no
    search/filter/sort/pagination yet - that's a dedicated later commit (goal 6)."""
    query = db.query(ExpenseReport)
    if user.role != Role.approver:
        query = query.filter(ExpenseReport.owner_id == user.id)
    if not include_archived:
        query = query.filter(ExpenseReport.archived_at.is_(None))
    return query.order_by(ExpenseReport.created_at.desc()).all()


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
