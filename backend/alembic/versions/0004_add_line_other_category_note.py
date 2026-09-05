"""add expense_lines.other_category_note

Optional elaboration field shown only when a line's category is "other" - the
fixed six-category list (Travel/Meals/Lodging/Supplies/Software/Other) can't
name everything, and the existing `description` field is already required on
every line regardless of category, so it wasn't the right place to force an
answer that should stay optional. Nullable, no default requirement, applies
regardless of category at the database/API level - the frontend is what
actually only shows the field when "Other" is selected.

Revision ID: 0004_add_other_category_note
Revises: 0003_enable_rls
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_add_other_category_note"
down_revision = "0003_enable_rls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("expense_lines", sa.Column("other_category_note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("expense_lines", "other_category_note")
