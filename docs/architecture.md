# Architecture

## What are the moving pieces, and how do they talk to each other?

Three pieces, two of them code in this repo:

1. **`frontend/`** — React 19 + TypeScript, built with Vite, no server-side rendering.
   A single-page app: React Router handles client-side navigation, `AuthContext`
   holds the current user and JWT in memory (backed by `localStorage` so a refresh
   doesn't force a re-login), and a small typed `fetch` wrapper (`src/api/client.ts`)
   is the only thing that talks to the backend.
2. **`backend/`** — FastAPI (Python), the only thing with a database connection or
   any business logic. Route handlers under `app/api/routes/` do request/response
   plumbing only; everything with an actual rule in it (lifecycle transitions,
   self-approval blocking, total recalculation, stale-alert math, dashboard
   aggregation) lives in `app/services/` and is unit-tested independently of HTTP.
3. **Postgres** — one database, no other persistence layer. SQLAlchemy models in
   `app/models/` are the single source of truth for the schema; Alembic migrations
   in `backend/alembic/versions/` are how that schema reaches a real database.

The frontend and backend talk over plain JSON HTTP: the frontend sends a JWT as an
`Authorization: Bearer` header on every request (issued once at login), the backend
verifies it and re-derives the current user from the database on every single
request — the token carries nothing but a user id, no role or permission claims, so
a role change or a report's state change is visible on the very next request rather
than waiting for a token to expire. See `test_role_change_takes_effect_without_a_new_token`
in `backend/tests/test_auth.py` for this actually being exercised, not just claimed.

## Where does each piece run?

- **Frontend**: static build (`vite build`) served by Vercel.
- **Backend**: a Render web service running `uvicorn app.main:app`. FastAPI's
  built-in `CORSMiddleware` is configured with the deployed frontend's exact origin
  (via the `CORS_ORIGINS` env var), not a wildcard, since the API accepts a real
  bearer credential.
- **Database**: a Supabase-hosted Postgres instance. Nothing else in this system
  reads or writes it directly — all access goes through the FastAPI backend.

Locally, all three are: Postgres in a Docker container, the backend on
`localhost:8000` via `uvicorn --reload`, and the frontend on `localhost:5173` via
`vite dev`, pointed at each other through `.env` / `.env.local`.

## Request path for one representative action, end to end

**An approver approves a report they don't own**, from click to database:

1. Browser: on `ReportDetail`, the "Approve" button is only rendered when
   `isApprover && !isOwner && report.status === "submitted"` (`ReportDetail.tsx`) —
   this is a UX nicety, not the actual enforcement.
2. `decideReport(reportId, "approved")` (`api/reports.ts`) sends
   `POST /reports/{id}/decide` with `{"decision": "approved"}` and the stored JWT in
   the `Authorization` header.
3. FastAPI resolves dependencies for `decide_report` (`api/routes/decisions.py`):
   `get_current_user` decodes the JWT, loads the `User` row fresh from Postgres;
   `get_visible_report` loads the `ExpenseReport` and 404s if this user can't see it
   (owner or any approver — an employee who isn't the owner gets a 404, not a 403,
   so a probing request can't even confirm the report exists).
4. The route calls `report_rules.decide(db, report, user, "approved")`
   (`services/report_rules.py`). This function — and only this function — knows the
   actual rule: the actor must hold the approver role, must **not** be the report's
   owner (raises a distinct `SelfApprovalError` if they are, checked by
   `test_self_approval_blocked_even_though_actor_is_an_approver`), and the report
   must currently be `Submitted`.
5. On success: `report.status` becomes `approved`, a `StatusEvent` row is inserted
   recording the transition and who made it. Nothing here is client-controlled —
   the "who" is the server-verified `user` from step 3, not anything the request body
   claimed.
6. The route commits, re-serializes the report (`services/serializers.py`), and
   returns it. The frontend re-fetches the report detail and re-renders.

Every other mutating action in this app (submit, reject, mark-paid, bulk-decide,
archive/restore, line CRUD, comments, alert dismissal) follows this same shape:
route does auth + visibility, a `services/` function does the actual rule, the
route commits and returns.

## What did we decide not to build?

- **No self-registration.** Users are seeded with hashed passwords; there's a login
  screen and nothing else. The brief only asks for "sign in."
- **No refresh-token rotation, no logout-everywhere, no rate limiting on login.**
  Session lifetime is a single `ACCESS_TOKEN_EXPIRE_MINUTES`-lived JWT; a demo app on
  a 2-day budget doesn't need a token-refresh dance. Logged as a known limitation.
- **No separate finance/admin role.** The brief describes exactly two roles; adding
  a third would be inventing scope, not meeting it.
- **No DB-level trigger enforcing the append-only timeline.** `StatusEvent` and
  `Comment` are append-only because no route exists to update or delete them — not
  because a trigger or revoked grant makes it physically impossible. A person with
  direct database access could still edit them. Acceptable given this app's threat
  model and time budget; a real production system with a genuinely adversarial
  insider threat would want the DB-level version too.
- **No approval-chain / multi-level approval, multi-currency, receipt OCR, or any of
  the stretch ideas.** All ten required goals came first; stretch ideas were never
  reached, by design — the brief itself says finishing fewer goals well beats
  finishing all ten badly, and stretch goals don't substitute for a required one
  either way.
