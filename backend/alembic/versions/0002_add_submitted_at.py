"""add expense_reports.submitted_at

Denormalized like total_cents (see docs/schema.md): the timestamp of the most recent
Draft->Submitted transition, set by services/report_rules.submit(). Exists so goal 6's
"sort by submitted date" is a plain indexed ORDER BY instead of a join/subquery against
status_events on every list request.

Revision ID: 0002_add_submitted_at
Revises: 0001_initial
Create Date: 2026-08-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_add_submitted_at"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("expense_reports", sa.Column("submitted_at", sa.DateTime(), nullable=True))
    op.create_index("ix_reports_submitted_at", "expense_reports", ["submitted_at"])


def downgrade() -> None:
    op.drop_index("ix_reports_submitted_at", table_name="expense_reports")
    op.drop_column("expense_reports", "submitted_at")
