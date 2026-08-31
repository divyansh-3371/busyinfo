from datetime import date, datetime

from sqlalchemy import BigInteger, Date, ForeignKey, Index
from sqlalchemy import Enum as SAEnum
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.models.enums import ReportStatus


class ExpenseReport(Base):
    __tablename__ = "expense_reports"
    __table_args__ = (
        Index("ix_reports_owner_id", "owner_id"),
        Index("ix_reports_status", "status"),
        Index("ix_reports_archived_at", "archived_at"),
        Index("ix_reports_submitted_at", "submitted_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[ReportStatus] = mapped_column(
        SAEnum(ReportStatus, name="report_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=ReportStatus.draft,
    )
    # Denormalized: the authoritative sum of this report's lines, recomputed by
    # app/services/report_rules.py on every line mutation. Never trust a client-sent
    # total — this column exists purely so search/sort/pagination (goal 6, "sort by
    # total amount") can be a single indexed ORDER BY instead of a correlated subquery
    # on every list request. See docs/schema.md for the trade-off.
    total_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    # Denormalized: set by services/report_rules.submit() on the most recent
    # Draft -> Submitted transition. See docs/schema.md.
    submitted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )

    owner = relationship("User", foreign_keys=[owner_id])
    lines = relationship(
        "ExpenseLine", back_populates="report", cascade="all, delete-orphan", order_by="ExpenseLine.date"
    )
    approver_links = relationship(
        "ReportApprover", back_populates="report", cascade="all, delete-orphan"
    )
    status_events = relationship(
        "StatusEvent",
        back_populates="report",
        cascade="all, delete-orphan",
        order_by="StatusEvent.created_at",
    )
    comments = relationship(
        "Comment", back_populates="report", cascade="all, delete-orphan", order_by="Comment.created_at"
    )
