from datetime import date, datetime

from sqlalchemy import BigInteger, Date, ForeignKey, Index
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.models.enums import ExpenseCategory


class ExpenseLine(Base):
    __tablename__ = "expense_lines"
    __table_args__ = (Index("ix_lines_report_id", "report_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("expense_reports.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    category: Mapped[ExpenseCategory] = mapped_column(
        SAEnum(
            ExpenseCategory, name="expense_category", values_callable=lambda e: [m.value for m in e]
        ),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    report = relationship("ExpenseReport", back_populates="lines")
