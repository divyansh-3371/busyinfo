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

Roughly 16-20 hours total, spread across 3-4 days at about 4-5 hours a day rather
than one long sitting. That pacing mattered more than the total: building the core
CRUD and lifecycle rules came first, but a real chunk of the time went into actually
using the deployed app afterward - logging in as an employee in one tab and an
approver in another and clicking through real flows - which is how most of the bugs
listed in `NOTES.md` under "Real bugs found and fixed after the initial build" were
actually found, not by re-reading the code.

## What would you do next, with another 12 hours?

If this were headed toward real company use rather than a demo, in priority order:

- **Notifications that leave the app.** Right now "you were rejected" only shows up
  as an in-app badge that the owner has to be logged in to see. A real reimbursement
  workflow needs an email (or Slack) the moment a decision is made - nobody should
  have to poll a web app to find out their expense got rejected.
- **A real automated frontend test suite** (Playwright or similar). QA so far is
  backend `pytest` (97 tests, covering every lifecycle rule and authz guard) plus
  manual/curl-based verification of the deployed API; the frontend has zero
  automated coverage, which is the single biggest risk in this codebase as it grows.
- **Multi-level approval for large amounts.** One flat approver tier is fine for a
  small team, but a company would want a report over some threshold to need a
  second sign-off - it's in the brief's own stretch list and is the most obviously
  "real" missing piece.
- **Move off JWT-in-response-body to an httpOnly cookie**, and add rate limiting on
  `/auth/login`. Both are documented trade-offs I made deliberately to fit the time
  budget (see `docs/decisions.md`), not oversights, but neither is something I'd
  ship to production as-is.
- **Audit export.** The append-only `status_events`/`comments` tables already make
  every decision traceable; the missing piece is just a "give finance a CSV of every
  decision in a date range" endpoint, which is a small addition on top of data
  that's already there.

## What are you least happy with in this codebase, and why?

No automated frontend tests, for the reason above - the backend has solid coverage,
but a regression in the React app would only be caught by clicking through it by
hand, which doesn't scale.

Separately, the hardest part of this project for me personally wasn't any single
feature - it was catching bugs that only exist in the gap between "the code does
what I described" and "a real person using it experiences what I intended." The
`needs_owner_attention` mark is the clearest example: my first version cleared the
flag the instant the owner opened the report, which sounds right on paper, but in
practice that's the same click as "read why I got rejected" - so the mark vanished
before anyone could ever actually see it highlighted in their list. That only
surfaced because I tested it live as a real user would, not from reading the diff.
Coordinating three separate free-tier services (Supabase, Render, Vercel) had a
similar flavor - each one's own quirks (Supabase's direct DB host being
IPv6-only and unreachable from Render, Render's inconsistent deploy times making
"did my fix actually go live yet" a recurring question) meant a lot of the real
debugging time went into verifying my own assumptions against the live system
rather than trusting that a green test suite meant the deployed app was correct.
