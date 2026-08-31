from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_visible_report
from app.db.session import get_db
from app.models.report import ExpenseReport
from app.models.user import User
from app.schemas.report import DecideRequest, ReportDetail
from app.services import report_rules
from app.services.report_rules import DomainError
from app.services.serializers import to_report_detail as _detail

router = APIRouter(prefix="/reports", tags=["decisions"])


@router.post("/{report_id}/submit", response_model=ReportDetail)
def submit_report(
    report: ExpenseReport = Depends(get_visible_report),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReportDetail:
    try:
        report_rules.submit(db, report, user)
    except DomainError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    db.commit()
    db.refresh(report)
    return _detail(report)


@router.post("/{report_id}/decide", response_model=ReportDetail)
def decide_report(
    payload: DecideRequest,
    report: ExpenseReport = Depends(get_visible_report),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReportDetail:
    if payload.decision not in ("approved", "rejected"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "decision must be 'approved' or 'rejected'.")
    try:
        report_rules.decide(db, report, user, payload.decision, payload.reason)
    except DomainError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    db.commit()
    db.refresh(report)
    return _detail(report)


@router.post("/{report_id}/pay", response_model=ReportDetail)
def pay_report(
    report: ExpenseReport = Depends(get_visible_report),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReportDetail:
    try:
        report_rules.mark_paid(db, report, user)
    except DomainError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    db.commit()
    db.refresh(report)
    return _detail(report)
