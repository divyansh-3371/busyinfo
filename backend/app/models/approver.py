from datetime import datetime

from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class ReportApprover(Base):
    """Many-to-many: which approvers are assigned to which reports. Assignment is a
    queue-filtering convenience, not an access gate — any approver (other than the
    report's owner) may still decide on any submitted report. See docs/decisions.md."""

    __tablename__ = "report_approvers"
    __table_args__ = (Index("ix_report_approvers_approver_id", "approver_id"),)

    report_id: Mapped[int] = mapped_column(
        ForeignKey("expense_reports.id", ondelete="CASCADE"), primary_key=True
    )
    approver_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    report = relationship("ExpenseReport", back_populates="approver_links")
    approver = relationship("User")
