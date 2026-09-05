"""add status_events.line_snapshot

Frozen copy of a report's lines at the moment of an approve/reject decision.
Lines are mutable once a report is back in Draft (a rejected report always
returns there), so without this, "what did the approver actually decide on"
would silently change under them the moment the owner edits anything and
resubmits. Nullable - only populated for the two decision transitions
(-> approved, -> rejected); every other transition (draft->submitted,
rejected->draft, approved->paid) leaves it null.

Revision ID: 0005_add_line_snapshot
Revises: 0004_add_other_category_note
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_add_line_snapshot"
down_revision = "0004_add_other_category_note"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("status_events", sa.Column("line_snapshot", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("status_events", "line_snapshot")
