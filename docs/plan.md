# Plan

## How the work was split into sessions

The full plan lives in `PLAN.md` at the repo root, written *before* any code, and
updated in place (checkboxes, running notes) as each piece landed — it's the actual
record of what was intended versus what happened, not reconstructed afterward.

Work was split into the two-day structure `PLAN.md` lays out, each day split into
two blocks, each block ending in one or more commits:

- **Day 1 AM** — repo/tooling scaffold (empty FastAPI app, empty Vite/React app),
  the full 7-table schema and its first migration, verified against a real local
  Postgres container rather than trusted on faith.
- **Day 1 PM** — auth end to end, the seed script, the `report_rules` service
  (lifecycle transitions + self-approval block) with its own unit tests, then the
  CRUD/lifecycle HTTP routes on top of it, then the first real frontend pages.
- **Day 2 morning** — the four goals flagged going in as the hardest: approver
  assignment, server-side search/filter/sort/pagination, bulk decide + CSV export,
  and stale alerts.
- **Day 2 afternoon** — the dashboard (the last of the ten goals), a dedicated
  edge-case audit against `PLAN.md`'s own edge-case list, the five docs you're
  reading now, and deployment.

Each commit in `git log` corresponds to one checklist item or a small tightly-related
group of them — the intent from the start was for the history itself to be legible
as the order things were actually built in, not squashed into one commit per day.

## What order was built in, and why

Foundations before features, in the most literal sense: schema → auth → business
rules → routes → UI, repeated per feature, rather than building the whole frontend
first against a mocked API or the whole backend first with no way to see it working.

Within that, `report_rules.py` (the lifecycle engine) was deliberately built and unit
tested *before* the HTTP routes that call it — the brief calls out several exact
rules (self-approval blocking, reject-requires-a-reason, the specific bulk-decide
result shape) precisely enough that getting the rule right in isolation, with tests
that don't depend on HTTP at all, felt lower-risk than writing it inline in a route
handler and discovering an edge case only via a failing request.

The four "harder required goals" (5/6/7/10) were done as a deliberate second pass
after the straightforward CRUD/lifecycle core was solid — each of them modifies or
depends on the same `expense_reports` table and its list query, so doing them after
the base shape was stable (rather than trying to design search/pagination/bulk-decide
simultaneously with the schema) kept each change small and independently testable.
The dashboard came last of the ten goals on purpose: it's a read-only aggregation
over everything else, so it benefited from the seed data and the rest of the schema
already being final.

## What was estimated versus what it actually took

The brief's own budget (roughly 12 hours over a week) was explicitly not the target
here — the actual constraint driving this build was a 2-day turnaround, and `PLAN.md`
budgeted accordingly: all four Day-1/Day-2 blocks above, sized to roughly half a day
each. In practice the ten required goals plus their tests fit inside that
without needing to cut anything — the biggest time sink relative to what was
expected was the local dev environment itself, not the application code: a native
Postgres service already listening on port 5432 on the build machine silently
intercepted the first several migration attempts (wrong-looking password-auth errors
that were actually a port collision, not a real credentials bug — see `NOTES.md`),
and Docker's registry pulls were unreliable enough on this network that pulling the
Postgres image took several retries before succeeding. Neither of those was visible
in the plan going in; both are now documented so they wouldn't cost time twice.

## What was cut when time was short

Nothing from the ten required goals was cut — all ten have a working implementation
with test coverage. What was deliberately scoped down, per the "must-have vs.
nice-to-have" split `PLAN.md` laid out from the start:

- **No automated frontend test suite.** Backend business logic and API behavior are
  covered by 82 pytest tests; the frontend was verified by a clean TypeScript build
  plus manual/API-level checking, not its own test runner. Given the time budget,
  the backend — where the brief's exact rules actually live — was judged the higher-
  value place to spend testing effort.
- **No DB-level enforcement of the append-only timeline** (see `docs/schema.md`) —
  enforced by the absence of an update/delete route, not a trigger.
- **Chart and UI styling stayed minimal** — functional, readable, not visually
  polished. This was the explicitly lowest-priority item in `PLAN.md`'s time budget,
  and time never actually ran short enough to need cutting it further than "minimal."
