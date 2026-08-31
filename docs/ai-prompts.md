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

## Deploying it for real, in a later session

The build above got the app committed and the pieces individually deploy-ready; a
separate session picked up from "where did I leave this" and actually finished
getting it live, debugging two real production bugs neither of us had hit before.

### Prompt
"where i left my project?"

### What I got
A status read of `PLAN.md`/`NOTES.md`/git log: all 10 goals implemented and
committed, deploy and final submission steps still unchecked.

### Prompt
"2" (picking "deploy" from a numbered list of what to do next)

### What happened
Claude checked the Supabase database directly (an MCP tool was already connected)
and found migrations and seed data were already live — ahead of what `PLAN.md`
still showed as unchecked. It then found `/auth/login` returning a bare `500` on
the live Render backend by curling it directly, and asked me to paste Render's logs
for the actual traceback rather than guessing at the cause.

### What went wrong, and what was corrected
1. **Render couldn't reach Supabase's DB at all**: `psycopg2.OperationalError:
   ... Network is unreachable` against Supabase's direct-connection host's IPv6
   address. Diagnosed from the real traceback, not guessed: Supabase's direct host
   resolves IPv6-only, and Render's outbound networking doesn't support it. Fixed by
   switching to Supabase's connection pooler host instead (same password, different
   host/port/username). Verified fixed by re-hitting `/auth/login` afterward and
   getting a real token back.
2. **Vercel 404'd on every route except `/`** (`/login`, etc.) once the frontend was
   deployed — caught by curling `/login` directly rather than assuming the deploy
   succeeded just because the build was green. Root cause: nothing told Vercel's
   static host to fall back to `index.html` for React Router's client-side routes.
   Fixed with a `frontend/vercel.json` rewrite rule; confirmed by curling the same
   URL again after the fix deployed (404 → 200).

### A mistake I made, not Claude
I pasted the real Supabase database password directly into the chat when giving
Claude the connection details. Claude flagged this itself, unprompted, and
recommended rotating the credential afterward. Done: the password has since been
reset in Supabase and `DATABASE_URL` updated on Render, re-verified live.

## Closing out testing, docs, and a pre-submission audit

### Prompt
"do pytest edgecase pass first"

### What I got
Not a rubber-stamp of the existing checkbox: Claude re-ran the suite, then went
bullet-by-bullet through `PLAN.md`'s own edge-case checklist (section 3) against
the actual test files rather than trusting that the earlier "82 tests" note meant
everything on that list was covered. It found one real, specific gap — nothing
asserted that a rejected/illegal transition leaves `status_events` untouched, true
only by code construction — and added a test for it rather than just noting the gap.

### Prompt
"presubmission audit"

### What I got
Every item in `PLAN.md`'s pre-deploy checklist actually executed, not just
checked off: `alembic upgrade head` and `seed.py` re-run against a genuinely fresh,
never-touched local database (row counts cross-checked against the live Supabase
DB), a frontend production build against the real deployed API (output hashes
compared byte-for-byte against what Vercel was actually serving), and a real
`git log -p` / `git log -S` secret scan across all history rather than just
checking that `.env` itself was never committed.

### What that audit caught
The scan found a real, serious problem: `NOTES.md`'s "password containing `@`"
example used my actual real Supabase database password, not a placeholder,
committed several commits back and live on the public GitHub repo the whole time.
Claude redacted it immediately, explained clearly that redacting the file doesn't
invalidate history that's already public, and flagged the password rotation as
urgent rather than routine cleanup. This is exactly the kind of thing an audit is
supposed to catch and didn't get softened in the report back to me.

## Making it look like a finished product

### Prompt
"the frontend is working fine, but looks broken make it more visually apealing
more sophisticated and aesthetic"

### What I got
Claude read every page's actual JSX and CSS before touching anything, and found
the real cause wasn't "needs more polish" but a leftover bug: `index.css` was still
the original Vite scaffold's landing-page stylesheet (a fixed 1126px centered
column, `text-align: center` on the whole app, a 56px hero heading, an unrelated
purple accent color) actively fighting the real app layout underneath it. It
replaced that with an actual design system — color/spacing/shadow tokens with
light and dark variants, a real header with active-page nav highlighting, cards for
every content section, color-coded buttons by intent (primary/danger/ghost) — then
verified the result with a clean production build before pushing, and confirmed
the live Vercel deploy was actually serving the new build rather than assuming a
push would take effect.

### A bug in Claude's own CSS, caught before it shipped
While reviewing its own redesign, Claude noticed a specificity conflict it had just
introduced: a new "mute the first paragraph on each page" rule would have overridden
the red error-message styling on any page where the error was the only paragraph
rendered (Dashboard, Reports list). It fixed the selector to explicitly exclude
`.form-error` before pushing, rather than after a review caught it separately.

### Prompt
"does the project checks everything on readme.md?"

### What I got
A full pass against every requirement in the brief, not just the 10 numbered
goals — process requirements (git history, the five docs files), hosting
requirements (secrets never in the repo — flagged as violated, per the audit
above), and submission mechanics. It also caught two things unprompted: this very
file not covering this session's work, and `docs/plan.md` claiming UI styling
"stayed minimal" when that was no longer true. Both are why this section and the
edit above it exist.
