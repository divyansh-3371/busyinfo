# Submission

Fill this in and commit it. This is the first file we open.

## Links

- **GitHub repository:** https://github.com/divyansh-3371/busyinfo
- **Live application:** https://busyinfo.vercel.app

## Notes for the reviewer

- The backend (https://busyinfo.onrender.com) is on Render's free tier, which sleeps
  after 15 minutes of inactivity. The first request after a cold start can take up to
  a minute to respond (Render is spinning the instance back up) - a slow first
  login is expected, not a broken deployment. Everything after that first request is
  normal speed.
- The API itself is browsable directly at https://busyinfo.onrender.com/docs
  (FastAPI's auto-generated Swagger UI) if you want to exercise endpoints without the
  frontend.
- Demo data (below) is seeded once via `backend/seed.py` and covers every one of the
  10 goals - draft/submitted/approved/rejected/paid reports, multiple approvers,
  comments, and reports old enough to trigger stale alerts.

## Demo credentials

All demo users share the password `password123`.

| Role | Email | Password |
|------|-------|----------|
| Employee | alice@example.com | password123 |
| Employee | bob@example.com | password123 |
| Approver | carol@example.com | password123 |
| Approver | dave@example.com | password123 |

## Stack

| Layer | What you used | Why |
|-------|---------------|-----|
| Frontend | React + TypeScript, Vite, React Router, Recharts | Fast dev loop, typed API contracts against the backend's Pydantic schemas, Recharts for the one required chart with minimal setup. |
| Backend | Python, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2 | FastAPI's automatic request validation and OpenAPI docs made the server-side authz/lifecycle rules (the actual ask in this brief) fast to write and easy to verify by hand against `/docs`. |
| Database | PostgreSQL (hosted on Supabase) | Relational integrity (FKs, CHECK constraints on the audit trail) matters more here than flexibility - reports, lines, approvers and status events are all strictly relational. |
| Hosting | Render (backend), Vercel (frontend), Supabase (database) | The three-service split the brief itself suggests, and it maps naturally onto having two separate codebases. |

## Goal checklist

Mark each honestly. Partial is fine — say what is partial.

| # | Goal | Status | Notes |
|---|------|--------|-------|
| 1 | Accounts and roles | Done | Login issues a JWT; every route re-derives the current role from the DB rather than trusting a token claim, so a role change takes effect immediately. Self-approval is blocked server-side, not just hidden in the UI. |
| 2 | Expense reports | Done | Create/edit (Draft only)/archive/restore, one owner per report, archived reports stay viewable. |
| 3 | Expense lines | Done | Add/edit/remove pre-submit only; `total_cents` is a server-recomputed, denormalized column - the client never sets it directly. |
| 4 | Report lifecycle with rules | Done | Draft → Submitted → Approved/Rejected → Paid enforced in `services/report_rules.py`; illegal transitions are rejected with a message; rejection requires a reason and returns the report to Draft. |
| 5 | Assigned approvers | Done | Any number of approvers per report; "assigned to me" is a queue filter, not an access gate - any approver (except the owner) can still decide on any submitted report. |
| 6 | Finding reports | Done | Server-side search (title), filters (status/owner/approver), sort (submitted date/status/total), and pagination with a total match count. |
| 7 | Bulk actions + CSV export | Done | Bulk approve/reject checks every report individually and names self-approval refusals specifically in the per-report result; CSV export of approved-but-unpaid reports. |
| 8 | Dashboard | Done | Awaiting-approval count, total due, approved/paid-this-week, status and category breakdowns, and an 8-week paid-per-week bar chart. |
| 9 | History you cannot rewrite | Done | `status_events` and `comments` are append-only tables (enforced by having no update/delete route), merged into one timeline view. |
| 10 | Stale-approval alerts | Done | Configurable day thresholds (`STALE_ALERT_DAYS`/`STALE_ALERT_SNOOZE_DAYS`); dismissal is personal per-approver state; a still-undecided report reappears after the snooze window. |

## How much time did you actually spend?

<Fill in - this is the one field only you can answer honestly.>

## What would you do next, with another 12 hours?

<Draft below based on what's actually in NOTES.md/PLAN.md as deliberate cuts - edit
this to reflect your own priorities before submitting:>

- A real automated frontend test suite (Playwright or similar) - QA so far has been
  backend `pytest` (97 tests) plus manual/curl-based verification of the deployed API;
  the frontend has no automated coverage at all.
- Rate limiting on `/auth/login`.
- Revisit the JWT-in-response-body-over-httpOnly-cookie trade-off if this ever needed
  to be more than a demo - it's XSS-exposed by design, documented in
  `docs/decisions.md`, and was chosen only to dodge cross-site cookie complexity under
  a 2-day budget.

## What are you least happy with in this codebase, and why?

<Draft below - edit to reflect your own view before submitting:>

No automated frontend tests is the biggest gap - the backend has solid coverage
(lifecycle transitions, self-approval blocks, bulk per-report results, stale-alert
window math, CSV export, authz guards), but a regression in the React app would only
be caught by clicking through it by hand.
