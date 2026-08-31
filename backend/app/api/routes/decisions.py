from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_visible_report, require_approver
from app.db.session import get_db
from app.models.report import ExpenseReport
from app.models.user import User
from app.schemas.report import (
    BulkDecideRequest,
    BulkDecideResponse,
    BulkDecideResultItem,
    DecideRequest,
    ReportDetail,
)
from app.services import report_rules
from app.services.report_rules import DomainError, SelfApprovalError
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


@router.post("/bulk-decide", response_model=BulkDecideResponse)
def bulk_decide(
    payload: BulkDecideRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_approver),
) -> BulkDecideResponse:
    """Approve or reject several submitted reports in one action. Every report is
    checked individually - one being illegal (not found, wrong status, or owned by
    the acting approver) never aborts the rest of the batch, and a report rejected
    specifically because the approver owns it is labeled that way (self_owned=True),
    distinct from any other kind of failure, per goal 7."""
    if payload.decision not in ("approved", "rejected"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "decision must be 'approved' or 'rejected'.")
    if not payload.report_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "report_ids cannot be empty.")

    results: list[BulkDecideResultItem] = []
    for report_id in payload.report_ids:
        report = db.get(ExpenseReport, report_id)
        if report is None:
            results.append(
                BulkDecideResultItem(report_id=report_id, ok=False, reason="Report not found.")
            )
            continue
        try:
            report_rules.decide(db, report, user, payload.decision, payload.reason)
            results.append(BulkDecideResultItem(report_id=report_id, ok=True))
        except SelfApprovalError as e:
            results.append(
                BulkDecideResultItem(report_id=report_id, ok=False, self_owned=True, reason=str(e))
            )
        except DomainError as e:
            results.append(BulkDecideResultItem(report_id=report_id, ok=False, reason=str(e)))

    db.commit()
    return BulkDecideResponse(results=results)
