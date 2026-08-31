# NOTES

Running log of assumptions, known limitations, and things to double-check before final
submission. Updated as the build happens, not reconstructed from memory at the end.

## Assumptions (from the initial requirements read-through)

- **Role model**: single `role` enum per user (`employee` | `approver`), not a set of
  roles. Approver is a strict superset of employee capabilities.
- **No self-registration**: users are seeded with hashed passwords; the app only has a
  login screen. The brief only asks for "sign in," never mentions signup.
- **Fixed expense categories** (not specified in the brief): Travel, Meals, Lodging,
  Supplies, Software, Other.
- **Stale-alert thresholds** (brief says "a set number of days" without a number):
  `STALE_ALERT_DAYS=3` (first alert), `STALE_ALERT_SNOOZE_DAYS=3` (reappear-after-dismiss),
  both env-configurable.
- **Report date range** is descriptive metadata for the report period; line item dates
  are not validated against it.
- **Comments** are visible to the report's owner and any approver (not just assigned
  ones), matching the "approvers see everything" pattern used for the submitted queue.
- **Assignment is a filter, not a gate**: any approver except the report's owner may
  decide on any submitted report, assigned or not.
- **Zero-line report can be submitted** (total 0), not blocked. Revisit if that turns
  out to be the wrong call.
- **Dismissing an already-dismissed, still-snoozed alert** resets `snoozed_until`
  forward (upsert on `(report_id, approver_id)`), rather than being a no-op.
- **Bulk reject uses one shared reason** for every report in the batch (a single
  `reason` field on the bulk-decide request), rather than a per-report reason. Bulk
  approve needs no reason at all, so this only affects bulk-reject, which seems like
  a reasonable simplification for a batch action.
- **Approver assignment isn't owner-restricted**: any approver can assign/unassign
  approvers on any report they can see (not just the report's owner), since it's a
  queue-management action among approvers, not something tied to report ownership.
- **Stale alerts (goal 10) - a deliberate interpretation of an exact-rule item**: the
  brief says "an approver can dismiss the alert for a report assigned to them," which
  could mean alerts are scoped to assignment. Instead: the alert list is global
  (every stale Submitted report, like every other "approvers see everything" list in
  this app), dismissal is personal per-approver state (one approver dismissing
  doesn't hide it for others), and any approver may dismiss any stale report -  not
  gated by assignment. Chosen for consistency with "assignment is a queue-filter
  convenience, not an access gate" used throughout, and because a strict assignment
  gate would leave an unassigned stale report with no one able to dismiss it at all.

## Architecture decisions worth remembering (full write-up goes in docs/decisions.md)

- Backend/frontend on different origins (FastAPI on Render, React on Vercel) → JWT is
  returned in the login response body and sent back as `Authorization: Bearer`, not an
  httpOnly cookie. Trade-off: token is readable by JS (XSS-exposed) in exchange for
  avoiding `SameSite=None` cross-site cookie + CORS-credentials complexity under a
  2-day deadline.
- `ExpenseReport.total_cents` is a denormalized column, recomputed by the server on
  every line mutation, rather than a computed-on-read aggregate — needed so "sort by
  total amount" (goal 6) is a plain indexed `ORDER BY`.
- `status_events` has a DB-level `CHECK` constraint requiring a `reason` whenever
  `to_status = 'rejected'`, on top of app-level validation.
- Append-only tables (`status_events`, `comments`) are enforced by *not having* an
  update/delete route — not by a DB trigger or revoked grants. A determined person with
  direct DB access could still edit them; that's outside this app's threat model given
  the time budget.

## Known limitations (deliberate, time-boxed cuts)

- No rate limiting on login.
- No automated frontend test suite — manual QA only (see PLAN.md testing strategy).
- Passlib dropped in favor of calling `bcrypt` directly: passlib 1.7.4 throws
  `(trapped) error reading bcrypt version` against bcrypt>=4.1 (a known, unfixed
  incompatibility — passlib is effectively unmaintained). Same security properties,
  one fewer dependency, no warning noise.

## Local dev environment quirks

- This machine has a native Windows PostgreSQL service already bound to port 5432, so
  the local dev Postgres container publishes on **5433** instead
  (`docker run ... -p 5433:5432 ...`, `DATABASE_URL` in `backend/.env` points at
  `127.0.0.1:5433`). Not relevant to deployment (Supabase supplies its own host/port),
  but worth knowing if migrations suddenly fail with a password-auth error that doesn't
  match `docker logs` on the actual container — that was a same-machine port collision,
  not a real credentials bug.
- `alembic/versions/0001_initial_schema.py` was hand-written rather than autogenerated
  (no live Postgres was reachable at the moment it was authored) and verified afterward
  against a real local Postgres 16 container.

## Deployment gotchas hit and fixed

- **Supabase DB password containing `@`**: a connection URL like
  `postgresql+psycopg2://postgres:Admin@ban16busyinfo@db.xxx.supabase.co:5432/postgres`
  misparses — the URL parser treats the *last* `@` as the credentials/host delimiter,
  so part of the password gets read as the start of the hostname. Fix: percent-encode
  special characters in the password (`@` → `%40`) before putting it in `DATABASE_URL`.
- **That fix then broke Alembic** with `ValueError: invalid interpolation syntax`:
  `alembic/env.py` was pushing the URL through `config.set_main_option()`, which
  stores values in a `ConfigParser` — and `ConfigParser` treats `%` as its own
  string-interpolation escape character, so a percent-encoded URL breaks it. Fixed by
  having `env.py` read `DATABASE_URL` directly from `get_settings()` and build the
  engine with `create_engine()` itself, never routing it through `ConfigParser` at
  all. See the commit for this fix and `backend/.env.example`'s updated comment.

## Fragility worth knowing about

- Stale-alert date math (`services/stale_alerts.py`) compares naive UTC datetimes,
  matching how `submitted_at` is actually stored (Postgres `TIMESTAMP WITHOUT TIME
  ZONE` strips tzinfo from whatever's written). Empirically verified against the local
  Postgres container that an aware-UTC datetime round-trips with no numeric drift
  (see the git history for that check). This assumes the database server's own
  timezone setting is UTC - true for this local container and for Supabase's default,
  but if that were ever not the case, the comparison would be silently off by the
  server's UTC offset. Worth a sanity check against the actual deployed Supabase
  instance during final deploy verification.

## To double-check before final submission

- Confirm the six assumed expense categories are acceptable, or adjust before seeding
  demo data with them baked in.
- Confirm the stale-alert day thresholds (3 / 3) are reasonable for the demo, or tune
  via env vars before the final deploy.
- Re-verify CORS_ORIGINS is set to the real deployed frontend URL (not just localhost)
  before considering deployment done.
- **Login/dashboard flow has not been clicked through in an actual browser** — no
  browser automation tool was available this session. Verified instead via FastAPI's
  TestClient and real HTTP calls (curl) against both dev servers, including a live
  CORS preflight check. Do a manual click-through early in Day 2 to catch anything a
  pure-HTTP check can't see (rendering issues, console errors, etc.).
