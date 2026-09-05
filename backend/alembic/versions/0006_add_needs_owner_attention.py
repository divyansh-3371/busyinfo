"""add expense_reports.needs_owner_attention

True from the moment an approver rejects a report until the owner either
views it or resubmits it, whichever comes first. Drives the per-row
"rejected" mark in the reports list and the nav badge count - deliberately
its own explicit column rather than derived from status_events at read time,
since "has the owner looked at this yet" isn't inferable from status history
alone (the report might have been rejected, viewed, then rejected again).

Revision ID: 0006_needs_owner_attention
Revises: 0005_add_line_snapshot
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_needs_owner_attention"
down_revision = "0005_add_line_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "expense_reports",
        sa.Column("needs_owner_attention", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("expense_reports", "needs_owner_attention")
