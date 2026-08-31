from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_visible_report, require_approver
from app.db.session import get_db
from app.models.report import ExpenseReport
from app.models.user import User
from app.schemas.report import ReportDetail, ReportListItem
from app.services import stale_alerts
from app.services.serializers import to_report_detail

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[ReportListItem])
def list_alerts(db: Session = Depends(get_db), user: User = Depends(require_approver)) -> list[ExpenseReport]:
    """Every stale Submitted report not currently dismissed by this approver. See
    services/stale_alerts.py for the interpretation this implements."""
    return stale_alerts.get_alerts_for_approver(db, user)


@router.post("/{report_id}/dismiss", response_model=ReportDetail)
def dismiss_alert(
    report: ExpenseReport = Depends(get_visible_report),
    user: User = Depends(require_approver),
    db: Session = Depends(get_db),
) -> ReportDetail:
    stale_alerts.dismiss(db, report, user)
    db.commit()
    db.refresh(report)
    return to_report_detail(report)
