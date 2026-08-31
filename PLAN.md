# PLAN.md — Expense Reimbursement System

Execution plan for Assignment 11. Built and deployed over a 2-day window. Checkboxes are
updated in place as work happens — this file is the running source of truth for progress,
not a static spec.

Companion running log: `NOTES.md` (assumptions, known limitations, things to double-check).

---

## 1. Architecture overview

**Stack** (rationale in `docs/decisions.md`):
- **Backend**: Python, FastAPI. Pydantic v2 for request/response schemas and validation.
  SQLAlchemy 2.x ORM + Alembic for migrations. `passlib[bcrypt]` for password hashing,
  `python-jose` for JWT. `pytest` + `httpx` (async test client) for tests.
- **Frontend**: React + TypeScript, built with Vite. React Router for pages, a small typed
  `fetch` wrapper for the API client, Recharts for the one required chart.
- **Database**: PostgreSQL, hosted on Supabase free tier.
- **Auth**: Login issues a JWT; the frontend and backend are on different origins
  (Vercel + Render), so the token is returned in the response body and sent back as an
  `Authorization: Bearer` header rather than an httpOnly cookie — a cross-site cookie needs
  `SameSite=None; Secure` plus careful CORS credential handling, which is more moving parts
  than the 2-day budget should spend on a demo app. This is a documented, deliberate
  trade-off (XSS-exposed token storage vs. cross-site cookie complexity) — see `decisions.md`.
- **Hosting**: backend on Render (free web service), frontend on Vercel, DB on Supabase —
  the three-service split the brief itself suggests, which now maps naturally onto having
  two separate codebases.

**Folder structure**
```
/backend
  app/
    main.py                  # FastAPI app, CORS, router registration
    core/
      config.py               # env var loading (Pydantic Settings)
      security.py             # password hashing, JWT issue/verify
    db/
      session.py              # SQLAlchemy engine/session
      base.py
    models/                    # SQLAlchemy models
      user.py  report.py  line.py  approver.py  status_event.py  comment.py  alert.py
    schemas/                   # Pydantic request/response models
    api/
      deps.py                  # get_current_user, role/ownership guards
      routes/
        auth.py
        reports.py             # list (search/filter/sort/paginate), create, edit, archive/restore
        lines.py                # add/edit/remove
        decisions.py            # submit, decide, pay, bulk-decide
        alerts.py
        dashboard.py
        export.py               # CSV
    services/
      report_rules.py          # lifecycle transition table, self-approval check, total calc
      stale_alerts.py          # stale window + snooze calculation
      csv_export.py
  alembic/versions/
  seed.py
  tests/
    test_report_rules.py
    test_bulk_decide.py
    test_stale_alerts.py
    test_csv_export.py
    test_authz.py
  requirements.txt

/frontend
  src/
    pages/
      Login.tsx  Dashboard.tsx  ReportsList.tsx  ReportDetail.tsx  NewReport.tsx  Alerts.tsx
    components/                # tables, forms, status badges, bulk-action bar, chart, alert banner
    api/                        # typed fetch client, one function per endpoint
    context/AuthContext.tsx      # holds JWT + current user, attaches Authorization header
    types/                       # TS types mirroring the Pydantic schemas
  package.json
  vite.config.ts

/docs                # the 5 required docs
PLAN.md  NOTES.md  SUBMISSION.md  README.md
```

**Data model** (detail in `docs/schema.md` once built):
- `User` (id, email, password_hash, role, name)
- `ExpenseReport` (id, owner_id, title, start_date, end_date, status, archived_at, created_at)
- `ExpenseLine` (id, report_id, date, amount_cents, category, description)
- `ReportApprover` (report_id, approver_id) — many-to-many join, unique on the pair
- `StatusEvent` (id, report_id, from_status, to_status, actor_id, reason, created_at) — append-only
- `Comment` (id, report_id, author_id, body, created_at) — append-only
- `AlertDismissal` (id, report_id, approver_id, dismissed_at, snoozed_until)

**Request path example** (approve a report): browser → React sends
`PATCH /reports/{id}/decide` with `Authorization: Bearer <jwt>` → FastAPI dependency
`get_current_user` verifies the JWT and loads the user from Postgres → `deps` checks
role == approver → `report_rules.decide()` checks `report.status == submitted` and
`report.owner_id != user.id` → SQLAlchemy transaction updates the report and inserts a
`StatusEvent` → JSON response → React re-fetches the list/detail.

---

## 2. Task breakdown (ordered checklist)

### Day 1 — foundations + core CRUD + lifecycle
- [x] Init git repo, initial commit (empty FastAPI app + empty Vite/React app scaffolds)
- [x] SQLAlchemy models for all 7 tables; first Alembic migration — verified against a
      local Postgres 16 container (upgrade/downgrade/re-upgrade all succeed). Supabase
      project creation itself is deferred to the deploy phase (section 5) since nothing
      before deployment actually needs the hosted DB — local Postgres is enough to build
      and test against.
- [x] Commit: schema + migration
- [x] `core/security.py`: password hashing (bcrypt directly, not passlib - see NOTES.md),
      JWT issue/verify; `api/deps.py`: `get_current_user`/`require_approver`
- [x] `POST /auth/login` + `GET /auth/me` (backend) + Login page + `AuthContext`
      (frontend) storing the JWT and attaching it to every request
- [x] Commit: auth working end-to-end against a manually-inserted test user — verified
      via TestClient and over real HTTP (uvicorn + Vite dev servers, live CORS
      preflight). Not yet clicked through in an actual browser (no browser tooling
      available this session) — flagged in NOTES.md as a manual check still owed.
- [x] `seed.py`: 4 users (2 employee, 2 approver), 16 reports covering every scenario
      goals 1-10 need to demo (draft, not-yet-stale/stale/reappeared-after-dismiss
      submitted, approved-unpaid, rejected-back-to-draft, approver-owns-a-report,
      archived, 8 weeks of paid history) — verified against local Postgres, safe to
      re-run
- [x] Commit: seed script
- [x] Role/ownership guard dependencies reused across every route (`get_visible_report`
      returns 404, not 403, for a report outside the viewer's visibility — avoids
      confirming another user's report id even exists)
- [x] Report CRUD: create, edit (Draft only), archive/restore (backend routes done;
      list/detail *pages* on the frontend are still the placeholder Dashboard — real
      UI is the next piece of work)
- [x] Expense line CRUD: add/edit/remove (pre-submit only), server-computed report total
- [x] Commit: report + line CRUD
- [x] `services/report_rules.py`: lifecycle transition table (Draft→Submitted→Approved/
      Rejected→Paid), self-approval block, reject-requires-reason, illegal-transition message
- [x] Submit / decide (approve/reject) / mark-paid endpoints wired to `report_rules`
- [x] `StatusEvent` row written on every real transition (append-only, no update/delete route)
- [x] Commit: lifecycle + audit trail — 28 tests passing (17 report_rules unit tests +
      11 API-level tests through real HTTP against real Postgres), covering the full
      lifecycle walk, self-approval block, reject-requires-reason, archive/restore
      idempotency, and the 404-not-403 visibility check
- [x] Basic report list + detail page (no search/filter yet) so the above is visually
      checkable — ReportsList, ReportDetail (line management, submit/decide/pay/
      archive/restore actions gated by the same rules as the backend, timeline), and
      NewReport, sharing a Layout/nav component. TypeScript build is clean; not yet
      clicked through in a real browser (same caveat as the auth milestone).

**Day 1 complete.** All of it verified except an actual browser click-through (no
browser tool available this session — see NOTES.md). 28 backend tests passing.

### Day 2 morning — the harder required goals
- [x] `ReportApprover` assignment endpoint/UI + "assigned to me" queue filter — any
      approver may manage assignments on any report (assignment is a queue-filter
      convenience, not an access gate); `PUT /reports/{id}/approvers` replaces the
      full set and validates every id is actually an approver
- [x] Server-side search (title), filters (status/owner/approver), sort (submitted date/
      status/total), pagination with total match count — one SQLAlchemy query, no
      full-table filtering in Python or in React. Added a denormalized
      `submitted_at` column (migration 0002) so sorting by submitted date is a plain
      indexed ORDER BY, matching the total_cents precedent.
- [x] Commit: assignment + search/filter/sort/pagination — 11 new tests (title search,
      status filter, zero-hit filter, pagination incl. out-of-range page, sort by
      total amount, invalid sort field rejected with 422, owner/approver filters,
      assigned-to-me, approver-id validation, role-gated assignment). 39 tests total.
- [x] `POST /reports/bulk-decide`: per-report check, structured result distinguishing
      "rejected — you own this report" from other outcomes (a dedicated `self_owned`
      boolean, not string-matching); bulk-select UI + result summary. A single shared
      `reason` applies to every rejection in one batch call — noted as a simplifying
      assumption in NOTES.md.
- [x] `GET /reports/export-due` CSV export of approved-but-unpaid reports — registered
      before the dynamic `/{report_id}` route (same reason `/approvers` is), header-only
      CSV for the zero-rows case, downloaded from the frontend via a fetched blob since
      the endpoint needs an Authorization header a plain link can't send
- [x] Commit: bulk actions + CSV export — 7 new tests (mixed-outcome batch incl. a
      nonexistent id, self-owned labeled distinctly from other failures, empty
      selection rejected, role-gated, CSV header-only when empty, role-gated export).
      46 tests total.
- [x] Comments endpoint (append-only) + timeline view merging `StatusEvent`s + `Comment`s,
      sorted (timeline view itself was already built in the Day 1 ReportDetail commit;
      this adds the missing write side)
- [x] Commit: comments + timeline — 4 new tests (owner and approver can comment,
      a non-owning employee gets 404 not 403, blank comment rejected, no PATCH/DELETE
      route exists at all — structural enforcement of append-only, not a per-request
      check). 50 tests total.
- [x] `services/stale_alerts.py`: days-in-Submitted calculation, dismiss endpoint writing
      `AlertDismissal` with `snoozed_until`, alert list excludes non-expired dismissals,
      nav badge count. Interpretation choice documented in the module and NOTES.md:
      the alert list is global (every stale Submitted report), dismissal is personal
      per-approver state, and any approver may dismiss any stale report — not
      restricted to reports assigned to them, for the same "assignment is a
      convenience, not a gate" reason used everywhere else.
- [x] Commit: stale alerts — 9 unit tests (not-yet-stale, just-stale, non-submitted
      never stale, dismissed-and-snoozed excluded, dismissed-and-expired reappears
      using an injected `now` rather than real clock waits, per-approver dismissal
      isolation, re-dismiss resets the snooze) + 2 API tests. 59 tests total.

**Day 2 morning complete.** All four "harder required goals" (5, 6, 7, 10) done and
tested. Frontend: alerts page + nav badge count for approvers.

### Day 2 afternoon — dashboard, edge cases, tests, docs, deploy
- [x] Dashboard aggregate endpoint: awaiting-approval count, total due, approved-this-week,
      paid-this-week, status breakdown, category breakdown, 8-week paid-per-week series.
      Scoped like everything else (employee sees own numbers, approver sees
      company-wide) — the dashboard wasn't singled out as an exception to that rule.
      "This week"/weekly buckets are trailing 7-day windows from `now`, not calendar
      weeks, documented in the module.
- [x] Dashboard page with Recharts bar chart, stat tiles, and status/category breakdowns
- [x] Commit: dashboard — 6 new tests (awaiting/total-due, zero-count statuses still
      present, category sums, this-week event counts, 8-bucket oldest-first series,
      employee-scoped-to-own). 65 tests total. Also nudged seed.py's weekly-paid
      timestamps 3 days off the exact bucket boundary after noticing the boundary-exact
      seed offsets could drift into the adjacent week purely from the gap between
      seeding and viewing — confirmed the dashboard logic itself was correct via the
      fixed-`now` unit tests before concluding it was a seed-data artifact, not a bug.
- [ ] Edge-case pass (see section 3) — implement or explicitly descope each one in `NOTES.md`
- [ ] `pytest` unit/API tests: lifecycle transitions, self-approval block, bulk per-report
      result shape, total calculation, stale-alert window math, CSV row generation, authz
      guard rejections
- [ ] Commit: tests
- [ ] Fill `docs/architecture.md`, `docs/schema.md`, `docs/plan.md`, `docs/decisions.md`
      (5 decisions, 1 reversed), `docs/ai-prompts.md` — from running notes kept during the
      build, not reconstructed from memory
- [ ] Commit: docs
- [ ] Deploy: Supabase prod DB → run Alembic migrations → seed prod DB → Render env vars
      (`DATABASE_URL`, `JWT_SECRET`, `CORS_ORIGINS`, `STALE_ALERT_DAYS`,
      `STALE_ALERT_SNOOZE_DAYS`) → Render deploy → Vercel env var (`VITE_API_BASE_URL`) →
      Vercel deploy
- [ ] Smoke-test the live URL end to end as both an employee and an approver
- [ ] Fill `SUBMISSION.md`: URLs, demo credentials per role, stack table, goal checklist,
      cold-start note (Render free web services sleep after inactivity)
- [ ] Commit: final docs + submission
- [ ] Pre-submission audit (Step 4 below)

---

## 3. Edge cases and failure modes

**Auth**
- Wrong password / unknown email → generic "invalid credentials" (don't leak which one was wrong).
- Missing/expired/tampered JWT → `401`, frontend treats it as logged out and redirects to
  login — never a 500.
- Every API route re-derives the user server-side from the verified JWT — never trusts a
  client-sent user id or role, even though the frontend also happens to know it.
- CORS restricted to the deployed frontend origin (and localhost in dev), not `*`, since the
  API accepts an `Authorization` header carrying real credentials.

**Accounts and roles**
- A user's `role` is read fresh from the DB on each request, not baked into a long-lived JWT
  claim that would survive a role change.
- Approver viewing/deciding on their own report → blocked server-side even if the request is
  crafted directly against the API (not just a hidden button in the React app).

**Expense reports**
- Title empty/whitespace-only → rejected (Pydantic validator).
- Start date after end date → rejected.
- Edit attempted on a non-Draft report → rejected with explanatory message.
- Archive an already-archived report / restore a non-archived one → no-op with a clear
  message, not a 500.
- Archived reports excluded from the default list and the approver queue, but still visible
  via detail/timeline if you have the id and are still authorized.

**Expense lines**
- Amount ≤ 0, non-numeric, or absurdly large (capped) → rejected.
- Category not in the fixed list → rejected (Pydantic enum).
- Date missing or unparseable → rejected.
- Adding/editing/removing a line on a Submitted+ report → rejected.
- Report with zero lines submitted → allowed, total is 0 — documented assumption, not
  silently blocked; revisit in `decisions.md` if it should be blocked instead.
- Total is recomputed server-side on every line add/edit/remove, never accepted from the
  client (even though the React app also computes it locally for instant UI feedback).

**Lifecycle**
- Non-owner tries to submit → rejected.
- Non-approver, or the owning approver, tries to decide → rejected with a message naming
  the reason.
- Reject without a reason → rejected (validation error).
- Decide on a report not in Submitted status → rejected, explanatory message.
- Mark-paid on a non-Approved report → rejected.
- Illegal transition attempts do not write a `StatusEvent` — only real transitions do.

**Assigned approvers**
- Assigning the same approver twice → idempotent (unique constraint on
  `(report_id, approver_id)`), not a duplicate row or a 500.
- Report with zero assigned approvers → still visible in the general submitted queue
  (assignment is a filter convenience, not a gate — assumption #7 from the requirements summary).
- Assigning a non-approver-role user → rejected.

**Finding reports (search/filter/sort/pagination)**
- Empty search string → no filter applied, not a query that matches nothing.
- Filter combination matching zero reports → empty state, not an error.
- Out-of-range page number → empty result with the correct total count, not a crash.
- Sort field/direction validated against an allow-list on the backend, never interpolated
  raw into the SQL.
- All filtering/sorting/pagination done in the SQLAlchemy query (`WHERE`/`ORDER BY`/
  `OFFSET`/`LIMIT`), never by fetching everything and filtering in React.

**Bulk actions**
- Empty selection submitted → rejected with a clear message, no-op.
- Mix of eligible and self-owned reports in one bulk request → per-report result array;
  self-owned ones explicitly labeled as rejected *because* of ownership, distinct from e.g.
  "already decided."
- A report id in the selection that doesn't exist or the approver can't see → reported as a
  distinct failure, not a silent skip or a 500 that aborts the whole batch.
- CSV export with zero due reports → valid CSV with header row only, not an empty/broken file.

**Dashboard**
- No data yet in some bucket (e.g., nothing paid this week) → renders as 0, not blank/NaN.
- Week boundaries defined consistently (UTC, fixed 7-day trailing windows) so "this week"
  numbers don't drift with server timezone.
- 8-week chart still renders (with zero-bars) for weeks with no paid reports.

**History / timeline**
- No API route ever exposes update/delete on `StatusEvent` or `Comment` — enforced by
  omission, not just by not building a button for it in React.
- Comment on an archived or terminal-state report → still allowed (history-keeping
  shouldn't be gated by report state) unless that proves out of scope, in which case
  documented as descoped.

**Stale alerts**
- Report becomes non-Submitted (approved/rejected) → immediately drops out of the alert
  list even if it was flagged before, regardless of any prior dismissal.
- Dismissal only valid for an approver assigned to that report (or, if unassigned reports
  appear in the general alert view, any approver — decide and document which).
- Dismissed alert reappears once `snoozed_until` has passed and the report is still
  Submitted — verified with a unit test using an injected fixed "now," not wall-clock timing.
- Dismissing an already-dismissed, still-snoozed alert → idempotent no-op or extends the
  snooze (pick one, document it).

**UI states (frontend)**
- Loading state for every async list/detail view.
- Error state (network failure, 401, 500) distinguished from empty state
  ("no reports found").
- No optimistic UI for status-changing actions — wait for the server's response given how
  much server-side rule-checking exists here.
- "Submit report" and "decide" buttons disable on click to prevent a double-submit; the
  real guarantee against a double-transition is the backend's lifecycle check, not the
  disabled button, which is only a UX nicety.
- 401 response from any request clears the stored JWT and redirects to login rather than
  looping or showing a raw error.

**Security basics**
- All input validated server-side with Pydantic (length caps, amount bounds, enum checks)
  — not just HTML form constraints in React.
- SQLAlchemy's parameterized queries throughout; no raw SQL string interpolation.
- `.env*` never committed (already gitignored); `SUBMISSION.md`/README never contain real secrets.
- Passwords hashed with bcrypt via passlib, never logged.
- JWT stored in the frontend in memory/localStorage (see the auth trade-off above) — no
  rate limiting on login given free-tier/demo scope, noted as a known limitation in
  `NOTES.md`, not silently ignored.

---

## 4. Testing strategy

**Backend tests (pytest + httpx)** — the business-rule surfaces most likely to hide a bug
and most likely to come up in the follow-up call:
- Lifecycle transition table: every legal transition succeeds, every illegal one is
  rejected with a message.
- Self-approval block, including an approver who is *also* assigned to their own report.
- Bulk-decide: mixed selection produces the correct structured per-report result.
- Report total calculation across add/edit/remove of lines, including the zero-line case.
- Stale-alert window math: not-yet-stale, just-stale, dismissed-and-still-snoozed,
  dismissed-and-snooze-expired — using an injected/mocked "now," not real clock waits.
- CSV export: correct rows for a known fixture set, correct header-only output for the
  empty case.
- Authz dependency: each guard rejects the roles/ownership combinations it should.

**Frontend**: no automated test suite given the 2-day budget — manual verification only,
noted as a deliberate scope cut in `NOTES.md`.

**Manual verification** (scripted checklist run locally, then again against the deployed app):
- Log in as each seeded role; confirm each sees only their own reports as an employee.
- Full lifecycle walk: create → add lines → submit → approve by a non-owning approver →
  mark paid.
- Attempted self-approval via a direct API call (not just the UI) confirmed blocked.
- Search/filter/sort/pagination against the seeded dataset, including a zero-hit filter combo.
- Bulk-select including one self-owned report; confirm the per-report message names it correctly.
- CSV download opens and matches the on-screen "due" list.
- Dashboard numbers cross-checked by hand against the seed data.
- Archive/restore a report, confirm it leaves/rejoins the default list.
- Dismiss a stale alert, fast-forward the snooze via a DB edit, confirm it reappears.

**Pre-deploy checklist**
- [ ] Backend starts cleanly (`uvicorn app.main:app`) with production env vars.
- [ ] `alembic upgrade head` applies cleanly to a fresh database.
- [ ] `seed.py` runs against a fresh database without manual fixups.
- [ ] `npm run build` (frontend) succeeds against the deployed API's `VITE_API_BASE_URL`.
- [ ] No secrets in git history (spot-check `.env` was never committed).
- [ ] All 10 goals walked manually against the local build once, end to end.

---

## 5. Deployment plan

1. Create Supabase project → note `DATABASE_URL`.
2. Run `alembic upgrade head` against the Supabase DB.
3. Run `seed.py` against the Supabase DB (demo users across both roles, reports spanning
   ~8 weeks and every status, enough volume that dashboard/chart/pagination are meaningful).
4. Push repo to a public GitHub repository (already required for submission).
5. Create a Render web service from the `backend/` directory: build
   `pip install -r requirements.txt`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`;
   set env vars (`DATABASE_URL`, `JWT_SECRET`, `CORS_ORIGINS`, `STALE_ALERT_DAYS`,
   `STALE_ALERT_SNOOZE_DAYS`) in Render's dashboard.
6. Create a Vercel project from the `frontend/` directory; set `VITE_API_BASE_URL` to the
   Render service's public URL.
7. Deploy both; verify build logs are clean on each.
8. Smoke-test the live frontend URL: log in as an employee and as an approver, run the full
   lifecycle once against production data, check the dashboard renders.
9. Note Render's free-tier cold start (services sleep after ~15 min idle; first request can
   take 30–60s to wake) in `SUBMISSION.md` so a slow first load isn't read as broken.

**Rollback / troubleshooting**
- Render and Vercel both keep prior deployments; a bad deploy is rolled back from either
  dashboard in one click — no rebuild needed.
- All schema changes are committed Alembic migrations, so a fresh Supabase project can be
  rebuilt from `alembic/versions/` + `seed.py` if the original ever needs replacing.
- Common failure modes to check first: missing/mistyped env var on Render or Vercel, CORS
  origin mismatch between the deployed frontend URL and the backend's `CORS_ORIGINS`,
  migration not applied to the deployed DB, seed not run against the deployed DB.

---

## 6. Time budget (2 days)

| Block | Focus | Must-have | Nice-to-have / first to cut |
|---|---|---|---|
| Day 1 AM | Scaffold both apps, DB schema/migrations, auth, seed | All | — |
| Day 1 PM | Report/line CRUD, lifecycle + audit trail | All | — |
| Day 2 AM | Assignment, search/filter/sort/pagination, bulk actions + CSV, comments/timeline, stale alerts | All | Polished bulk-result UI copy |
| Day 2 midday | Dashboard + chart | All | Chart styling; falls back to a plain numbers table if Recharts eats too much time |
| Day 2 PM | Edge cases, backend tests, docs, deploy, submission | All | Any frontend automated tests; broader backend coverage beyond the business-rule core in section 4; extra manual-QA polish |

All 10 numbered goals are must-have — they're the stated cutoff for a complete submission,
and partial credit for 8-of-10-done-well beats 10-of-10-done-badly per the brief itself, so
nothing here is planned as "skip a whole goal." If Day 2 PM runs over, the descoping order
(last first) is: chart visual polish → bulk-action UI copy → broader backend test coverage
→ UI styling polish. The 10 functional goals, server-side authorization, and the 5 docs are
never cut — everything above is sequenced so that if only some finish, what's left
unfinished is honestly reflected in `SUBMISSION.md`'s goal checklist rather than
misrepresented as done.
