"""enable row level security on every table

Supabase auto-exposes a PostgREST REST API over every table in the `public`
schema, reachable with just the project's anon/publishable key - independent of
and unrelated to this app's own JWT auth. With RLS disabled (the SQLAlchemy/
Alembic default - it isn't something you get for free), that API could read or
write every row in every table here, including `users.password_hash`, to
anyone holding that key. Flagged by Supabase's own advisor, confirmed by a
"critical issue" email, fixed by enabling RLS with zero policies.

Safe with no policies added: this app's backend connects with a privileged
Postgres role (the actual DATABASE_URL, not the anon/authenticated roles used
by Supabase client libraries), and Postgres table owners bypass RLS by default.
So this closes off exactly the PostgREST path this app never uses, without
touching how the FastAPI backend itself talks to the database - verified live
(login, report listing, and the dashboard's multi-table aggregate) after this
was first applied directly against the running database, before being captured
here so a fresh deploy doesn't silently reintroduce the same gap.

Revision ID: 0003_enable_rls
Revises: 0002_add_submitted_at
Create Date: 2026-09-02
"""
from alembic import op

revision = "0003_enable_rls"
down_revision = "0002_add_submitted_at"
branch_labels = None
depends_on = None

TABLES = [
    "alembic_version",
    "users",
    "expense_reports",
    "expense_lines",
    "report_approvers",
    "status_events",
    "comments",
    "alert_dismissals",
]


def upgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;")


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY;")
