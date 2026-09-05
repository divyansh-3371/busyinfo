# Decisions

## Decision 1

- **Chose:** FastAPI (Python) backend + a separate React/TypeScript frontend.
- **Rejected:** A single Next.js (TypeScript) full-stack app — one codebase doing
  both the UI and the API routes.
- **Why:** The initial plan, written before any code, *was* Next.js full-stack:
  fewer moving parts, one deploy target, one language. That plan was reversed after
  explicitly deciding Python should be the base language for the backend. Once the
  backend was Python, the choice became "Python backend + Python frontend
  (Streamlit) or Python backend + a separate JS frontend" — see Decision 2.
- **Later reversed:** Yes — this *is* the reversal. The original `PLAN.md`
  architecture section (Next.js, one deploy target) was rewritten in full before any
  implementation began, once the language constraint changed. Nothing about the ten
  functional goals changed; only the implementation language and, as a consequence,
  the deploy topology (one Vercel target → Render + Vercel + Supabase).

## Decision 2

- **Chose:** A separate React/TypeScript SPA calling the FastAPI backend over JSON.
- **Rejected:** A single Streamlit app with no separate API layer — Streamlit UI
  code calling the database/service layer directly, in-process.
- **Why:** Streamlit was seriously on the table — it would have collapsed the
  backend and frontend into one deploy target and one language throughout, and its
  native tables/forms/metrics map onto this app's CRUD-and-dashboard shape well.
  It was set aside in favor of keeping the FastAPI/React split already designed
  under Decision 1: a real REST API is more conventional to demo, easier to test at
  the HTTP boundary independent of any particular UI, and closer to what the
  brief's own suggested stack (a separate frontend and backend) assumes. This was an
  explicit fork put to the person directing the build, not a default assumed
  silently.

## Decision 3

- **Chose:** JWT returned in the login response body, sent back as
  `Authorization: Bearer <token>`, stored client-side (in-memory + `localStorage`
  for persistence across a refresh).
- **Rejected:** An httpOnly session cookie set by the backend.
- **Why:** The frontend (Vercel) and backend (Render) are different origins. An
  httpOnly cookie across different origins needs `SameSite=None; Secure` plus
  careful CORS-credentials configuration — solvable, but it's real setup cost for a
  2-day build with no corresponding security requirement in the brief. The
  Authorization-header approach avoids all of that. The honest trade-off: a token
  in `localStorage` is readable by any JavaScript running on the page (XSS-exposed),
  where an httpOnly cookie would not be. Accepted for this app's threat model and
  time budget; would not make the same call for a system handling more sensitive
  data or with more time to spend on it.

## Decision 4

- **Chose:** `bcrypt` called directly for password hashing.
- **Rejected:** `passlib`'s `CryptContext` wrapper around bcrypt.
- **Why:** `passlib` 1.7.4 throws `(trapped) error reading bcrypt version` against
  `bcrypt >= 4.1` — a real, currently-unfixed incompatibility (passlib is
  effectively unmaintained). Discovered immediately, while writing the very first
  password-hashing smoke test, before it was ever committed. Calling `bcrypt`
  directly gives the identical security property with one fewer dependency and no
  warning noise.

## Decision 5

- **Chose:** `expense_reports.total_cents` and `expense_reports.submitted_at` are
  denormalized columns, recomputed by `services/report_rules.py` whenever they'd
  change.
- **Rejected:** Computing both on read — `SUM(lines.amount_cents)` and a lookup into
  `status_events` for the most recent submit event.
- **Why:** Goal 6 requires server-side sorting by both total amount and submitted
  date, in the same query that also does text search, multiple filters, and
  pagination. A cached, indexed column makes that a plain `ORDER BY`; computing
  either value on read would mean a join or correlated subquery on every single list
  request. The cost is a real one, made explicit rather than hidden: if a line were
  ever mutated through a path that skipped `recalculate_total`, the cached total
  would silently drift from the truth. No route currently allows that, but nothing
  enforces it at the database level either — see `docs/schema.md`.

## Decision 6

- **Chose:** The stale-alert list is global (every stale Submitted report, visible
  to every approver), and dismissal is personal per-approver state — any approver
  may dismiss any stale report's alert, not only ones assigned to them.
- **Rejected:** Restricting both the alert list and the dismiss action to reports a
  given approver is actually assigned to.
- **Why:** This is a direct interpretation call on one of the brief's explicitly
  called-out "exact rules" ("an approver can dismiss the alert for a report assigned
  to them"), made because the alternative has a real gap: a stale report with zero
  assigned approvers would be an alert nobody could ever dismiss under the stricter
  reading. The chosen interpretation is also the one consistent with how assignment
  behaves everywhere else in this system — a queue-filtering convenience, never an
  access gate (goal 5's "assigned to me" is a filter on the same full queue every
  approver already sees, not a restriction on who may act). Documented in
  `services/stale_alerts.py` in case a reviewer reads it the other way.
