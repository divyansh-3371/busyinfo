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
  `postgresql+psycopg2://postgres:MyP@ssword@db.xxx.supabase.co:5432/postgres`
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
- **Render couldn't reach Supabase's direct DB host at all**: every request touching
  the DB failed with `psycopg2.OperationalError: ... Network is unreachable` against
  `db.<ref>.supabase.co`'s IPv6 address, even though `/health` (no DB call) worked
  fine and the same host was reachable from the Supabase MCP tooling (which goes
  through Supabase's management API, not a raw Postgres connection, so it never hit
  this). Root cause: Supabase's direct connection host resolves IPv6-only, and
  Render's outbound networking doesn't support IPv6. Fix: switch `DATABASE_URL` to
  Supabase's **connection pooler** (Supavisor) host instead - same password,
  different host/port/username (`postgres.<project-ref>` @
  `aws-0-<region>.pooler.supabase.com:6543`). That host is IPv4-reachable. Confirmed
  fixed by re-testing `/auth/login` against the live deploy afterward.
- **Vercel 404'd on every route except `/`** (`/login`, `/reports/1`, etc.): Vercel's
  static file server looks for a literal file at the request path and 404s if it
  isn't there - it has no idea `BrowserRouter` (client-side routing) wants those
  paths handled by `index.html`. Fixed with a `frontend/vercel.json` rewriting every
  path to `/index.html`. Confirmed fixed by curling `/login` before (404) and after
  (200) the fix deployed.

## Real bugs found and fixed after the initial build

Two later QA passes, kept here rather than only in commit messages since these are
exactly the kind of thing this file exists to track.

- **The test database session didn't match production's.** `db/session.py` runs
  every real session with `autoflush=False`; the test fixture (`tests/conftest.py`)
  never set it, defaulting to `True`. That gap hid a real bug: `update_line` was
  missing the `db.flush()` that `add_line`/`delete_line` both already have before
  `recalculate_total()`. In production this meant editing a line's amount
  recomputed the report's total from the line's *old* amount and permanently
  committed that wrong number - a real break of goal 3's exact promise, invisible
  in every test because autoflush covered for it. Fixed the bug, then fixed the
  test session to match production exactly, which is what actually surfaced this
  (it broke 4 previously-green tests). Two more instances of the identical
  missing-flush shape (`report_rules._log_event`, `stale_alerts.dismiss`) were
  hardened the same way, though neither was reachable as a live bug through the
  actual HTTP routes today.
- **Login was case-sensitive on email.** Postgres' default text `=` is
  case-sensitive; `Alice@Example.com` or `ALICE@EXAMPLE.COM` were rejected as
  wrong credentials with the exact right password. Confirmed live against the
  deployed backend before fixing. Fixed with a case-folded comparison
  (`func.lower(User.email) == email.strip().lower()`) - only the comparison
  changed, stored emails are untouched.
- **Pydantic's own validation errors were invisible on the frontend.** FastAPI
  shapes a `field_validator`/`model_validator` rejection's `detail` as an array
  of `{msg, loc, ...}` objects, not the plain string our own `HTTPException`
  calls use - `apiFetch` only ever checked for a string, so blank-title,
  bad-date, invalid-amount, oversized-description, and blank-comment errors all
  silently fell back to "Request failed (422)" instead of the specific message
  already written for them. This touched nearly every form in the app. Confirmed
  by comparing a live Pydantic 422 against a live custom-HTTPException response -
  genuinely different shapes.
- **Whitespace-only search silently returned zero results**, contradicting this
  file's own "empty search = no filter" assumption from the edge-case list - `q`
  wasn't trimmed before the truthiness check or the `ILIKE` pattern.
- A search race condition in `ReportsList`: a new request fires on every
  keystroke with no protection against out-of-order responses - a slow response
  for an earlier, shorter search term could land after a newer one's and
  overwrite it. Fixed with a monotonic request-sequence guard.
- `formatCents` used the viewer's own browser locale for a USD-only app, so the
  same amount could render differently depending on who's looking. Pinned to
  `en-US`.
- **Row Level Security was disabled on all 8 tables in Supabase** - flagged by
  Supabase's own advisor the very first time this database was checked in this
  session (before any of the above), left open at the time as the user's call
  since enabling it blindly can lock out access if done wrong. Supabase later
  emailed about it directly as a critical issue, at which point it was actually
  fixed: `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` on all 8 tables, no
  policies added. Safe specifically because this app's backend connects with a
  privileged Postgres role that bypasses RLS by default - the fix only closes
  off Supabase's separate, auto-generated public PostgREST API (reachable with
  just the project's anon key), which this app never uses at all. Verified live
  afterward: login, report listing, and the multi-table dashboard aggregate all
  still return 200 with RLS on.
- **Login leaked which emails were registered via a timing side-channel.**
  `if user is None or not verify_password(...)` short-circuits on `or` - an
  unknown email skipped bcrypt entirely (a fast DB miss), while a real email
  with the wrong password always ran the full ~100-300ms bcrypt comparison.
  The response body was already identical either way (tested), but the
  *timing* wasn't, and that's enough on its own to let an attacker enumerate
  registered accounts by measuring response latency across a list of
  candidate emails - a real precursor to targeted credential-stuffing or
  phishing, worse given there's no login rate limiting (a separate, already-
  documented limitation). Found via a dedicated security review, not the
  general bug-hunt passes above. Fixed by always calling `verify_password`
  exactly once - against the real user's hash, or a precomputed
  `DUMMY_PASSWORD_HASH` when no user was found - so both paths pay the same
  bcrypt cost regardless of outcome. Checked for the same pattern anywhere
  else bcrypt is used in the app: nowhere - `/auth/login` is the only route
  that ever calls `verify_password` at all, since there's no signup or
  password-reset route to have the same bug. Covered by a timing-based
  regression test (`test_unknown_email_takes_as_long_as_wrong_password`,
  generous 2x tolerance to avoid CI flakiness) rather than just a code-review
  fix taken on faith.

Checked and specifically ruled out, not left unexamined: a password over
bcrypt's 72-byte limit already returns a clean 401 (the existing
`except ValueError` in `verify_password` catches it); duplicate report ids in
one bulk-decide request already resolve correctly, one at a time; archived
reports staying fully editable is consistent with this app's own "flags filter,
never gate" pattern used everywhere else, not a bug.

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
