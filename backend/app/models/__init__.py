"""Import every model here so a single `import app.models` registers all tables on
Base.metadata — this is what alembic/env.py imports for autogenerate/target_metadata."""
from app.models.alert import AlertDismissal
from app.models.approver import ReportApprover
from app.models.comment import Comment
from app.models.line import ExpenseLine
from app.models.report import ExpenseReport
from app.models.status_event import StatusEvent
from app.models.user import User

__all__ = [
    "User",
    "ExpenseReport",
    "ExpenseLine",
    "ReportApprover",
    "StatusEvent",
    "Comment",
    "AlertDismissal",
]
