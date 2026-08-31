from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_visible_report
from app.db.session import get_db
from app.models.comment import Comment
from app.models.report import ExpenseReport
from app.models.user import User
from app.schemas.report import CommentCreate, CommentOut

router = APIRouter(prefix="/reports/{report_id}/comments", tags=["comments"])


@router.post("", response_model=CommentOut, status_code=status.HTTP_201_CREATED)
def add_comment(
    payload: CommentCreate,
    report: ExpenseReport = Depends(get_visible_report),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Comment:
    """Anyone who can see the report (its owner, or any approver) can comment.
    Append-only: there is deliberately no PATCH/DELETE here - see docs/decisions.md."""
    comment = Comment(report_id=report.id, author_id=user.id, body=payload.body)
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment
