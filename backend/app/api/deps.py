from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.enums import ReportStatus, Role
from app.models.report import ExpenseReport
from app.models.status_event import StatusEvent
from app.models.user import User

_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolves the current user from the Authorization header on every request.
    Never trusts anything the client claims about its own identity or role beyond the
    bare user id encoded in a validly-signed token - role and every other attribute are
    re-read from the database each time."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise unauthorized
    user = db.get(User, user_id)
    if user is None:
        raise unauthorized
    return user


def require_approver(user: User = Depends(get_current_user)) -> User:
    if user.role != Role.approver:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires the approver role.",
        )
    return user


def _has_ever_decided(db: Session, report: ExpenseReport, user: User) -> bool:
    """Has this user personally approved or rejected this specific report at some
    point, regardless of what's happened to it since? A past decision is yours to
    review forever, independent of the report's current status - the reason it's
    back in Draft after a rejection shouldn't erase your own ability to see the
    decision you made and exactly what you were looking at when you made it (see
    StatusEvent.line_snapshot)."""
    return (
        db.query(StatusEvent.id)
        .filter(
            StatusEvent.report_id == report.id,
            StatusEvent.actor_id == user.id,
            StatusEvent.to_status.in_([ReportStatus.approved, ReportStatus.rejected]),
        )
        .first()
        is not None
    )


def get_visible_report(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ExpenseReport:
    """Fetches a report the current user is allowed to *see* - their own (any
    status), another employee's once it's no longer a Draft, or one they've
    personally decided on before (approved or rejected it at some point), no
    matter what its current status is. A Draft is otherwise the owner's private,
    unfinished work - "approvers can view and decide on reports submitted by
    other employees" (the brief's own wording) never included seeing it before
    that - but an approver's *own past decision* is a fact about them, not about
    the report's current state, and stays visible to them regardless. Returns 404
    (not 403) when it's not visible, so a request for someone else's report id
    doesn't confirm that id even exists - including someone else's draft, which
    would otherwise leak "a report exists here" even without exposing its content.

    This only governs visibility. Whether the user may *edit* or *decide on* the
    report is a separate, stricter check made in each route (see report_rules) -
    this exception is read-only in practice, since decide() still independently
    requires the report to currently be Submitted."""
    report = db.get(ExpenseReport, report_id)
    visible = report is not None and (
        report.owner_id == user.id
        or (user.role == Role.approver and report.status != ReportStatus.draft)
        or _has_ever_decided(db, report, user)
    )
    if not visible:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")
    return report
