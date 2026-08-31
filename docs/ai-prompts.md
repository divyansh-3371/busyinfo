# AI prompts

This project was built with Claude Code, directing it at a high level rather than
line-by-line — a small number of architecture-level prompts, then one long
"build it" instruction that Claude executed autonomously (scaffolding, schema,
routes, tests, docs) while checking its own work at each step: running the actual
test suite, running the actual migration against a real local Postgres, and
correcting itself before committing rather than after. What follows is the real
prompt sequence in order, grouped by what I was trying to get out of each one.

## Understanding the assignment and getting a plan before any code

### Prompt
A long structured prompt (the one supplied with the assignment) asking Claude to:
read `submission.md`/`README.md` in full, summarize the explicit and implicit
requirements and any ambiguities back to me with stated assumptions, then produce a
detailed `PLAN.md` (architecture, task breakdown, edge cases, testing strategy,
deployment plan, time budget) and wait for approval before writing any code.

### What I got
A clear requirements summary (correctly identifying the 10 numbered goals as the
real spec, and the process requirements — git history, the five `docs/` files — as
equally graded), a list of genuine ambiguities with stated assumptions for each
(the category list isn't specified anywhere in the brief; the stale-alert day
thresholds aren't given a number; whether assignment gates decisions isn't fully
spelled out), and a full `PLAN.md` proposing a Next.js (TypeScript) full-stack
architecture with Supabase + Vercel hosting.

### What I corrected
Nothing wrong yet — the plan was coherent and the requirements summary held up
through the whole build without needing revision. The architecture itself changed
next, though, which is its own story below.

## Choosing the tech stack

### Prompt
"what is the tech stack you are using?"

### What I got
A table explaining the Next.js/Supabase/Vercel choice from the plan above, and
explicit acknowledgment that it deviated from the brief's own suggested three-service
split (Supabase + Render + Vercel) in favor of one deploy target.

### Prompt
"can i use python as base language?"

### What I got
Claude flagged this as a real architecture fork rather than a small tweak, and
asked a clarifying question first (Django+HTMX monolith vs. FastAPI+React SPA vs.
FastAPI+Jinja2) instead of guessing. I chose FastAPI + React. Claude then rewrote
`PLAN.md`'s entire architecture section: FastAPI/SQLAlchemy/Alembic backend,
React/TypeScript/Vite frontend, and — because the two now live on different
origins — swapped the planned auth mechanism from an httpOnly cookie to a JWT
bearer token, with the reasoning written into the plan rather than just the
outcome.

### What I corrected
This *is* the corrected thing: the entire original Next.js architecture was
discarded before a single line of implementation code existed. Nothing about the
ten required goals changed, only the implementation language and deploy topology.
It's logged as the one required "later reversed" entry in `docs/decisions.md`.

### Prompt
"can i use streamlit for frontend?"

### What I got
Another explicit fork rather than a silent swap: Claude laid out two real options
(a single Streamlit app with no separate API, versus Streamlit only replacing the
React layer on top of the existing FastAPI backend) with the trade-offs of each,
and asked which I wanted before touching `PLAN.md`.

### What I corrected
I answered "keep it as it is" — declining Streamlit and staying with FastAPI +
React. No plan changes were needed since nothing had been built yet on the Streamlit
path; this is recorded as a rejected alternative in `docs/decisions.md` rather than
silently omitted, since it was a real option that was seriously discussed.

## Building it

### Prompt
"so start creating the project according to the plan.md"

### What I got
The entire application, built and committed incrementally against `PLAN.md`'s own
checklist — one git commit per task or small group of related tasks, the checklist
itself checked off in place as each one landed, `NOTES.md` kept running alongside it
for assumptions and known limitations. This one instruction covered the whole
two-day build: schema and migration (verified against a real local Postgres, not
just written and assumed correct), auth, the lifecycle/business-rule engine and its
unit tests, CRUD routes, the frontend pages, then the four harder goals (assignment,
search/filter/sort/pagination, bulk-decide + CSV, stale alerts), the dashboard, a
dedicated edge-case audit against `PLAN.md`'s own edge-case list, and these five docs.

### What went wrong along the way, and what was corrected
Several concrete things broke or were caught as wrong during this single long
build, each fixed before moving on rather than left for later:

1. **Password hashing.** The first implementation used `passlib`'s `CryptContext`
   wrapper around bcrypt. The very first smoke test threw
   `(trapped) error reading bcrypt version` — a known, unfixed incompatibility
   between `passlib` 1.7.4 and `bcrypt >= 4.1`. Caught before it was ever committed;
   switched to calling `bcrypt` directly, which dropped a dependency and the warning
   entirely (`docs/decisions.md`, Decision 4).
2. **Docker image pulls.** Pulling the local Postgres image for dev/testing failed
   repeatedly (`failed to copy: httpReadSeeker...`) on this network. Retried rather
   than giving up on local verification — Docker caches completed layers, so each
   retry made progress until it succeeded.
3. **A misleading local error.** The first `alembic upgrade head` against the local
   dev database failed with a Postgres password-authentication error. That looked
   like a real credentials bug in the app; it was actually an unrelated native
   Windows Postgres service already listening on the default port, silently
   intercepting the connection. Diagnosed by testing authentication *from inside the
   target container itself* before assuming the application code was wrong, then
   fixed by moving the dev container to a different local port. Logged in `NOTES.md`
   so it wouldn't cost time twice.
4. **A docstring that went stale mid-task.** The first migration's docstring said it
   hadn't been verified against a live Postgres — true at the moment it was
   *written*, but no longer true by the time the same commit's testing actually
   verified it against a real local instance. Caught before committing; the commit
   was amended rather than shipping documentation that contradicted the very
   verification performed for it.
5. **A seed-data artifact, not a bug — but checked to be sure.** The seeded
   weekly-paid demo data landed exactly on a dashboard chart bucket boundary, so
   which of the 8 weekly buckets a given report appeared in was sensitive to the
   small time gap between seeding and later querying. Before assuming this was a
   seed-data quirk, the dashboard's bucket math was re-verified against its own
   fixed-`now` unit tests (which passed on exact boundaries) to confirm the
   aggregation logic itself was correct — only then was the seed data adjusted
   (offsets nudged 3 days off the boundary) rather than the application code.

None of these were prompted individually — they surfaced while executing the single
"build it" instruction, and in each case the fix (and, in the docstring and seed-data
cases, the *reasoning* for why it was a fix rather than a bug) is visible in the
relevant commit message, not just asserted here after the fact.
