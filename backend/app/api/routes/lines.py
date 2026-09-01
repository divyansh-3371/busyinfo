from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_visible_report
from app.db.session import get_db
from app.models.enums import ReportStatus
from app.models.line import ExpenseLine
from app.models.report import ExpenseReport
from app.models.user import User
from app.schemas.report import ExpenseLineIn, ExpenseLineOut
from app.services.report_rules import recalculate_total

router = APIRouter(prefix="/reports/{report_id}/lines", tags=["lines"])


def _require_editable(report: ExpenseReport, user: User) -> None:
    if report.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the report's owner can edit its lines.")
    if report.status != ReportStatus.draft:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Cannot edit lines on a report that is currently {report.status.value}.",
        )


@router.post("", response_model=ExpenseLineOut, status_code=status.HTTP_201_CREATED)
def add_line(
    payload: ExpenseLineIn,
    report: ExpenseReport = Depends(get_visible_report),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExpenseLine:
    _require_editable(report, user)
    line = ExpenseLine(report_id=report.id, **payload.model_dump())
    db.add(line)
    db.flush()
    recalculate_total(report, db)
    db.commit()
    db.refresh(line)
    return line


@router.patch("/{line_id}", response_model=ExpenseLineOut)
def update_line(
    line_id: int,
    payload: ExpenseLineIn,
    report: ExpenseReport = Depends(get_visible_report),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExpenseLine:
    _require_editable(report, user)
    line = db.get(ExpenseLine, line_id)
    if line is None or line.report_id != report.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Line not found.")
    for field, value in payload.model_dump().items():
        setattr(line, field, value)
    # Without this, recalculate_total's query wouldn't see the amount_cents change
    # just made above - the app's real sessions run with autoflush=False (see
    # db/session.py), so the edit stays pending until an explicit flush or commit.
    # add_line/delete_line already flush before recalculating; this one didn't.
    db.flush()
    recalculate_total(report, db)
    db.commit()
    db.refresh(line)
    return line


@router.delete("/{line_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_line(
    line_id: int,
    report: ExpenseReport = Depends(get_visible_report),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    _require_editable(report, user)
    line = db.get(ExpenseLine, line_id)
    if line is None or line.report_id != report.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Line not found.")
    db.delete(line)
    db.flush()
    recalculate_total(report, db)
    db.commit()
