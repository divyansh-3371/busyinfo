from datetime import datetime

from sqlalchemy import ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class AlertDismissal(Base):
    """One row per (report, approver) who has dismissed the stale-approval alert.
    Dismissing again (e.g. after it reappears) updates dismissed_at/snoozed_until in
    place rather than accumulating rows — see docs/decisions.md."""

    __tablename__ = "alert_dismissals"
    __table_args__ = (
        UniqueConstraint("report_id", "approver_id", name="uq_alert_dismissals_report_approver"),
        Index("ix_alert_dismissals_report_id", "report_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("expense_reports.id", ondelete="CASCADE"), nullable=False
    )
    approver_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    dismissed_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    snoozed_until: Mapped[datetime] = mapped_column(nullable=False)

    report = relationship("ExpenseReport")
    approver = relationship("User")
