from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.models.enums import ReportStatus


class StatusEvent(Base):
    """Append-only audit trail entry. No route ever updates or deletes a row here —
    see docs/decisions.md for why that's enforced by omission rather than a DB trigger."""

    __tablename__ = "status_events"
    __table_args__ = (
        Index("ix_status_events_report_id", "report_id"),
        # DB-enforced, not just app-validated: a rejection must always carry a reason.
        CheckConstraint(
            "to_status != 'rejected' OR reason IS NOT NULL",
            name="ck_status_events_reject_requires_reason",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("expense_reports.id", ondelete="CASCADE"), nullable=False
    )
    from_status: Mapped[ReportStatus | None] = mapped_column(
        SAEnum(ReportStatus, name="report_status", values_callable=lambda e: [m.value for m in e]),
        nullable=True,
    )
    to_status: Mapped[ReportStatus] = mapped_column(
        SAEnum(ReportStatus, name="report_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    report = relationship("ExpenseReport", back_populates="status_events")
    actor = relationship("User")
