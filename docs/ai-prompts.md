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

## Fixing a real bug and a UX pass

### Prompt
"in the project there is no option for signup or register for new user and also
if i enter wrong credentials it stuck in a loop fix this"

### What I got
Two different answers for two different things, not a blanket "fixed both." The
missing signup was correctly identified as intentional, not a bug - the brief's
goal 1 only ever says "people sign in," and it's already `NOTES.md`'s first
documented assumption - so Claude explained that instead of silently building a
registration flow that wasn't asked for. The wrong-credentials issue turned out to
be a real bug: `apiFetch` treated *every* `401` response as a session expiring,
including the login endpoint's own "wrong password" rejection - clearing a token
that was never set, and showing "Session expired - please log in again" instead
of the backend's actual "Invalid email or password." Not an infinite loop
technically, but a wrong, misleading message on every retry, which is exactly
what reads as being stuck. Fixed by only treating a `401` as session-expiry when a
token was actually sent with the request - a login attempt never sends one.

### Prompt
"check for small fixes that provides seamlessness in the user experience. check
for all the things happening before or after an event... if i select one report
it says bulk but for single selection it should not say bulk"

### What I got
A systematic pass through every mutating action's before/during/after state, not
just the one example given. Beyond the bulk-label wording (now "Approve"/"Reject"
for one report, "Bulk approve"/"Bulk reject" for more than one), it found several
real state-consistency bugs on its own: changing the sort field didn't reset
pagination the way every other filter already did; a stale bulk-result banner
could linger after changing filters; and, the more serious one - the add-line and
add-comment forms in `ReportDetail` cleared themselves *unconditionally* after a
submission attempt, because the shared `runAction` helper swallowed its own
errors. That meant a rejected expense line (bad amount, invalid date) silently
wiped the entire form the user had just typed, with no way to recover it. Fixed by
having `runAction` report success/failure and only clearing input on success.
Also added a busy state to the one action that didn't have one (CSV export), and
guarded every form's submit handler against double-firing via Enter, since a
button's `disabled` attribute doesn't stop a form's `onSubmit` event from firing
again while a request is already in flight.

### What I corrected
Nothing here - this was Claude's own audit surfacing bugs I hadn't noticed myself,
not a correction of something it got wrong.

## Two rounds of "find every bug like that one"

### Prompt
"DID YOU CHECK FOR EVERY CASE SCENARIO WHERE CODE CAN BE BROKEN LIKE WHEN I SAY
THAT IF I FEED WRONG PASSWORD IT GOES INTO LOOP THEN YOU FIX IT, SO I WANT YOU TO
FIND ALL THE BUGS LIKE THIS IN THE PROJECT SO IT CAN BE FULL PROOF"

### What I got
Rather than re-reading code for more surface-level issues, Claude checked whether
the test suite's database session actually matched production's. It didn't - the
app's real sessions run `autoflush=False` (`db/session.py`), but the test
fixture never set it, defaulting to `True`. Tightening the test session to match
production exactly, then re-running the suite, broke 4 previously-green tests -
each pointing at a real bug that autoflush had been silently papering over:

- `update_line` was missing a `db.flush()` that `add_line`/`delete_line` both
  already had before recalculating the report's total. In production, editing a
  line's amount recomputed the total using the line's *old* amount and
  permanently committed that wrong number - breaking goal 3's exact promise
  ("total is always the sum of the lines"), invisible in every test because
  autoflush was covering for it.
- Two more instances of the same missing-flush shape
  (`report_rules._log_event`, `stale_alerts.dismiss`) - not reachable as live
  bugs through the actual HTTP routes today (both already commit before
  anything reads the result back), but one refactor away from becoming one.

Also found, by reasoning about the code rather than the test gap: `ReportsList`
fires a new search request on every keystroke with no protection against
responses arriving out of order - a slow response for an earlier, shorter search
term could land after a newer one's and silently show stale results.

### Prompt
"RECHECK FOR ANY ERROR PRONE AREA, VALIDATIONS, CASE SENSITIVITY AND MANY SMALL
EDGE CASES THAT CAN BREAK THE CODE. THINK BY YOURSELF OF SUCH CASES AS YOU ARE
FROM THE TESTING TEAM, TEST IT RIGEROUSLY"

### What I got
This round was tested live against the deployed app with real requests, not just
read from source - which is what actually confirmed each hypothesis before
touching any code:

- **Login was case-sensitive on email.** `Alice@Example.com` or
  `ALICE@EXAMPLE.COM` got rejected as wrong credentials with the *exact right
  password*, because Postgres' default text `=` is case-sensitive and nothing
  normalized either side. Confirmed with three live curl calls before fixing -
  a real lockout, not a theoretical one.
- **Pydantic's own validation errors were being silently discarded on the
  frontend.** FastAPI shapes a `field_validator`/`model_validator` rejection's
  `detail` as an array of `{msg, loc, ...}` objects, not a plain string - the
  frontend's error handler only ever checked for a string, so blank-title,
  bad-date, invalid-amount, oversized-description, and blank-comment errors
  all fell back to a useless "Request failed (422)" instead of the specific
  message Pydantic had already written. Confirmed by comparing a live Pydantic
  422 response against a live custom-HTTPException response side by side -
  they're genuinely different shapes, and only one was handled.
- **A whitespace-only search silently returned zero results**, contradicting
  the app's own documented "empty search = no filter" promise - confirmed live
  (`q=""` returned everything, `q="   "` returned nothing) before fixing.
- `formatCents` used the viewer's own browser locale for a USD-only app -
  same amount, different-looking output depending on who's looking.

Also specifically tested and *ruled out* a couple of tempting-looking bugs
before claiming anything was wrong with them: a password over bcrypt's 72-byte
limit returns a clean 401, not a crash (already guarded); duplicate report ids
in one bulk-decide request already resolve correctly report-by-report.

### What I corrected
Nothing here either - both rounds were Claude finding real bugs on its own
initiative, verifying each one live before fixing it, and reporting the things
it checked and found fine alongside the things it fixed.

## A Supabase security alert, and a dedicated security review

### Prompt
"i got mail from supabase that my project has security vuneralibility. fix it"
(with a screenshot of Supabase's "Table publicly accessible" critical alert)

### What I got
Confirmation this was the exact Row Level Security gap Claude's own Supabase
tooling had already flagged the very first time it checked the database,
earlier in this session - left open at the time pending a decision on whether
enabling it blindly was safe. Fixed properly this time: RLS enabled on all 8
tables with no policies (safe here specifically because this app's backend
connects with a privileged role that bypasses RLS, so it only closes off
Supabase's separate public API), verified live that the actual app still
worked afterward, and - unprompted - turned it into a real Alembic migration
and back-stamped the live database's migration history to match, since the
fix had only been applied directly and a fresh deploy would have silently
reintroduced the exact same gap otherwise.

### Prompt
"check for more security vunerables"

### What I got
A dedicated security-review pass (a different mode than the general bug-hunt
audits above - narrower, deeper, focused specifically on exploitable
vulnerabilities: injection, auth bypass, secrets, data exposure) surfaced one
real, concrete finding: `/auth/login`'s `user is None or not verify_password(...)`
short-circuits on `or`, so an unknown email skips bcrypt entirely while a real
email with the wrong password always pays the full hash cost. The response
body was already identical either way; the timing wasn't - enough on its own
to let an attacker enumerate which emails are registered by measuring
response latency. Reported first as a structured finding (file, line,
severity, exploit scenario, fix) before touching any code.

### Prompt
"fix it and do the same for rest"

### What I got
The fix - always calling `verify_password` once regardless of whether a user
was found, against a precomputed dummy hash when there wasn't one - plus the
"do the same for rest" half actually executed as a real second pass: grepped
for every other place bcrypt/password verification happens in the app to
check for the identical pattern elsewhere. Found none - `/auth/login` is the
only route that ever calls `verify_password` at all, since there's no signup
or password-reset route to have the same bug in. Reported that honestly
rather than padding the fix list with unrelated changes to look thorough.
Backed by a timing-based regression test with a deliberately generous
tolerance (2x) to avoid flaky CI while still failing hard against the actual
bug, where the real gap was roughly two orders of magnitude, not a borderline
difference.

### What I corrected
Nothing here either - found and fixed on Claude's own initiative once asked
to look, verified with both a live check and an automated test rather than
taken on faith.

### Prompt
"keep going"

### What I got
A second real, concrete finding from the same kind of adversarial pass:
`export_due`'s CSV writer put `report.title` into a cell with no
neutralization at all. A title is set by any employee with no character
restrictions, and this export exists specifically to be opened in Excel or
Google Sheets by an approver - both treat a cell starting with `=`, `+`, `-`,
or `@` as a formula to evaluate on open. This is a known, named vulnerability
class (CSV/Formula Injection, CWE-1236), not something invented for this
project. Fixed with a small `_csv_safe()` helper applied to every string
column the export writes, backed by a regression test, verified against the
full suite before committing. Also explicitly checked for other places
user-controlled text leaves React's automatic escaping into some other
consuming format (an email, a PDF, another export) - there are none; this
CSV is the only place in the whole app where that happens.

## Two product questions, from actually using the app

### Prompt
"whenever i create new report there is no option assign approver and whenevr
i choose other in reason (there should be option to write reason which is
titally optional)" (with a screenshot of a report's "Assigned approvers"
section showing no picker)

### What I got
Two different answers, not one blanket fix. The missing assign-approver
picker on your own report turned out to be intentional, existing design -
`docs/decisions.md` already documents assignment as an approver-only
queue-management action, not something a report's owner does themselves -
so Claude explained that and asked whether to change it rather than silently
"fixing" a deliberate choice. The "other" question needed a clarifying
question first (the phrase "reason" didn't match anything literally in the
app), which turned out to mean the expense-line category dropdown - when
"Other" is picked, wanting an optional field to say what it actually is.
That one was a genuine, reasonable gap: added `other_category_note` as a
real nullable column (migration 0004), tested upgrade/downgrade against a
fresh database, applied to the live Supabase database the same way as the
RLS fix, wired into the frontend so the field only appears for "Other" and
clears itself if you switch away.

### Prompt
"approver shouldnt see draft report untill it submitted, is it fine?"

### What I got
Confirmation this was a real gap, not a false alarm - checked the actual
code (`get_visible_report`) and found an existing test that locked in the
wrong behavior on purpose: an approver could already see another employee's
never-submitted Draft, in both the report-list and by direct id, contradicting
the brief's own wording ("reports submitted by other employees"). Unlike the
assign-approver question above, there was no documented rationale anywhere
defending this - it was a real bug, not a design choice - so Claude
recommended fixing it plainly rather than treating it as equally-valid
either way.

### Prompt
"yes"

### What I got
The fix in both places that needed it (`get_visible_report` and
`list_reports`), which - because both routes and the comment/assignment
routes all share that one dependency - correctly closed the gap everywhere
at once without touching each route individually. Five existing tests had
been quietly relying on the old behavior (an approver commenting on or
assigning themselves to another employee's still-unsubmitted draft) and
needed their setup fixed to submit the report first; their actual
assertions didn't need to change, just the precondition. Also made an
explicit, stated judgment call rather than silently expanding scope: left
the dashboard's aggregate counts showing all statuses company-wide,
including drafts, since a number doesn't expose a draft's content the way
opening the report itself would - flagged this to double-check rather than
just doing it.

### What I corrected
Nothing in either exchange - one was Claude correctly declining to change a
documented design decision without asking, the other was Claude confirming
a real gap the person using the app had already correctly spotted, then
fixing it precisely at its source.

## Revisiting the assignment question, and a UI cleanup that followed from it

### Prompt
"so shouldnt it be decided by owner rather than approver?"

### What I got
A real reconsideration, not a repeat of the earlier answer. Since assignment
grants no actual power (self-approval is blocked independently, regardless of
who's assigned), there's no security argument for keeping it approver-only -
letting the owner route their own report to whoever should review it is
reasonable on its own merits. Claude asked one scoping question (owner-only,
replacing approvers' ability, vs. both) rather than guessing, then implemented
"both": the report's own owner can now manage assignments alongside any
approver, `/reports/approvers` opened to any authenticated user (just names,
nothing sensitive) so an owner can populate the picker, and `docs`/`NOTES.md`
updated to record the revision rather than silently overwriting the original
decision.

Two existing tests had encoded the old, narrower rule and needed updating -
one directly (an owner setting their own approvers now succeeds instead of
403), and one indirectly: `test_role_change_takes_effect_without_a_new_token`
had used `/reports/approvers` purely as a convenient stand-in "some
approver-only endpoint" to prove a role change takes effect without a new
login - once that endpoint stopped being approver-only, the test's actual
point (JWTs don't cache roles) needed a different probe
(`/reports/export-due`, which still is approver-only), not weakening the
thing being tested.

### Prompt
"why draft option is there in approver's portal if he cant see draft
reports" (screenshot of the status filter dropdown)

### What I got
Confirmation this was a real, if smaller, inconsistency left over from the
draft-visibility fix: an approver selecting "draft" from the status filter
can only ever see their *own* drafts (everyone else's are invisible to them
per that fix), which makes the filter look broken rather than just narrow.
Fixed by hiding that one option from the dropdown specifically for
approvers - employees keep it, since for them it means exactly what it
looks like.

### Prompt
"and what is the meaning of assigned approvers?"

### What I got
A plain-language explanation of the concept itself - assignment as a
filtering convenience, not an access gate - which is what led directly into
the next prompt above questioning who should control it.

### What I corrected
Nothing in this whole thread - each prompt built on the last (what does this
mean, why does that look wrong, why is control the way it is) and Claude's
answers held up under each successive question rather than needing revision.

## A real regression, then a genuine feature request

### Prompt
"rejection leads to this and when a report rejected owner should be notified
that approver reject the report with that reason so that he can make
changes in it but instead it goes directly into draft mode which can be go
overlook easily" (screenshot of a bare "Report not found" error)

### What I got
Two different things addressed as two different things, not conflated into
one fix. The screenshot turned out to be a real regression Claude had
introduced with the earlier draft-visibility fix: an approver rejecting a
report correctly sends it back to Draft, but that also makes it instantly
invisible to that same approver (they don't own it, it's no longer
non-draft) - the page's own post-action reload then hit that same
visibility rule, 404'd, and the whole page broke into a scary error for an
action that had actually just worked. Fixed at the one shared choke point
(`runAction`) every mutating action already goes through: a 404 on the
reload immediately after a successful action is the action's own expected
consequence, not a failure - leave for the reports list instead of showing
an error.

The notification idea was treated separately, as a real but genuinely
open-ended feature request rather than something to fold into the bug fix -
this app sends no email or push notifications at all, and building either
would be well beyond scope. Claude asked which of three reasonably-scoped
options to build (a nav badge matching the existing Alerts pattern, showing
the rejection reason directly in the list, or both) instead of guessing, and
built the badge: a new `/reports/needs-attention-count` endpoint counting
reports currently in Draft *because* they were rejected (not just any
unsubmitted draft), shown as the same visual badge pattern approvers already
get for stale alerts - but not role-gated, since anyone who owns a report,
approvers included, can have it rejected.

### What I corrected
The regression, immediately and without being asked twice - it was Claude's
own fix that caused it, found by the user actually using the app rather than
by any of Claude's own testing passes, which is itself worth being honest
about: live verification after each change catches a lot, but not
everything, and a real user clicking through it is still how this one
surfaced.

## Decision snapshots, and why a rejected version should stay rejected

### Prompt
"why it says rejected draft and also if i reject a report why it disappereard
from approvers portal" (screenshot of a timeline showing "submitted →
rejected" then "rejected → draft" as two separate lines)

### What I got
Two separate answers again, not one merged explanation. The two timeline
lines were confirmed as intentional - they're two genuinely different facts
(the decision itself, with its reason; then the automatic, mechanical return
to Draft), and collapsing them would lose exactly the kind of detail goal 9
asks the timeline to keep. The disappearing-from-the-portal question was
identified as the direct, correct consequence of the draft-visibility rule
from several prompts earlier, applied with no exception - which prompted
Claude to ask whether that was actually the wanted behavior or whether the
rejecting approver specifically should be able to keep watching it.

### Prompt
"the approver should see it as rejected and can see the report which he
rejected even though it changes in draft mode the approver just see the
version which he rejected as rejected and then when the owner resubmit it,
still the rejected one should be there as rejected"

### What I got
Recognition that this was asking for something more specific than "let the
approver see the live draft" - a permanent, frozen record of what was
actually rejected, immune to whatever the owner edits afterward. Claude laid
out a concrete three-part plan (snapshot the lines at decision time onto
that status event, a narrow permanent-visibility exception for whoever
personally decided on a report, and surfacing the frozen snapshot in the
timeline) and confirmed the shape of it before touching the schema, rather
than assuming a smaller interpretation and building the wrong thing.

### Prompt
"do it in the best way possible"

### What I got
The full three-part plan, plus symmetry Claude added on its own initiative:
both approvals *and* rejections get snapshotted, not just rejections, even
though an approved report's lines can never actually be edited again anyway
(there's no path back to Draft from Approved) - reasoned through and stated
explicitly as "this half is for consistency, not because it fixes a live
bug," rather than silently doing more than asked without saying so. A new
migration (tested upgrade/downgrade against a fresh database, then applied
to the live database the same way as the earlier ones), a new visibility
exception in `get_visible_report` scoped as narrowly as the request itself
(only someone who personally decided on *this* report, not approvers in
general), and the frozen snapshot rendered in the timeline behind a
collapsed "view the lines rejected" disclosure rather than always-expanded
clutter.

### Prompt
"why should i refresh to get new status or report it should auto refresh
whenever approver or owner does something" (sent mid-turn, while the
snapshot feature was still being built)

### What I got
A correctly-scoped answer to a different question, not folded into the
snapshot work already in progress: real push updates (websockets) would be
disproportionate new infrastructure for this app, but polling is cheap and
directly answers what was actually asked. Added silent background polling
to `ReportDetail` (10s) and `ReportsList` (10s), plus the nav badges (30s) -
all reusing the same guarded reload functions already in place, so a poll is
invisible unless something actually changed. Also connected it correctly to
the earlier reject-navigation fix: a poll that lands on a report which just
became invisible (someone *else's* decision this time, not the viewer's own
action) gets the same graceful "leave for the list" treatment, not a
jarring error, since the same root cause applies either way.

### What I corrected
Nothing wrong here - each of these was Claude asking exactly one clarifying
question at exactly the point real ambiguity existed (what "the version he
rejected" actually meant), then building precisely that once confirmed,
including deciding on its own where symmetry was worth adding and saying so
plainly.

## A visible mark for a rejected report, with a specific clear condition

### Prompt
"first of all mark the report which is rejected so that owner knows which
report got rejected and remove the mark right after i interact with it"
(screenshot of a reports list where a rejected-then-draft report was
indistinguishable from any ordinary unfinished draft)

### What I got
A real, specific two-part spec, not a vague "show it somehow" - a visible
mark on the row, cleared specifically by the owner interacting with that
report, not by any other event. Implemented as a new boolean column
(`needs_owner_attention`) rather than trying to infer "has this been seen"
from existing history, since that state genuinely doesn't exist anywhere
else in the data model: set true on rejection, cleared by whichever happens
first between the owner viewing the report or resubmitting it. Rendered as a
small red "rejected" tag next to the status badge on that one row, and
scoped so it only ever shows to the actual owner - an approver browsing the
same list doesn't see it on someone else's report.

### What I corrected
Nothing - built exactly to the two conditions specified (mark it, clear it
on interaction), tested both independently (viewing without resubmitting,
resubmitting without ever viewing) rather than assuming either one alone
was sufficient.
