# Assignment 11 — Expense Reimbursement

## The scenario

Picture a mid-sized company where employees pay for travel, meals and supplies out of pocket and get
reimbursed by emailing a manager a spreadsheet of expenses with photos of receipts attached. The
manager replies "approved" to the thread, forwards it to finance, and finance eventually issues a
payment whenever they get to it.

The result is predictable. Finance cannot say how much the company currently owes in unpaid
reimbursements without opening every recent email thread and adding it up by hand. A manager who
also travels for work ends up approving their own expense report because nobody is checking who sent
the "approved" reply against who submitted the spreadsheet. A rejected report gets a one-line reply
explaining what was wrong, the employee means to fix it, and the whole thread quietly disappears
into an inbox never to be resubmitted.

They want one system: employees submit expense reports with individual line items, an approver who
is not the employee reviews and decides on each one, and finance can see exactly what is owed and to
whom at any moment. Anyone should be able to tell what is awaiting approval and what is approved but
not yet paid, without searching an inbox. Build the system that replaces the email thread.

## What it must do

Everything below is required. Several of the ten spell out exact rules — what happens on an illegal
move, what a bulk action must report back, when a dismissed alert is allowed to reappear — and those
specifics are the actual ask, not just the bold headline in front of them.

1. **Accounts and roles.** People sign in with an email and password, and there are at least two
roles — an employee role and an approver role. Every user, regardless of role, can create, edit and
submit their own expense reports, and see only their own. Approvers can additionally view and decide
on reports submitted by other employees, approving, rejecting, or marking an approved one as paid —
never their own, even though they hold the approver role. The difference must be enforced on the
server, not just hidden in the interface.

2. **Expense reports.** Employees create expense reports for themselves with a title and a date
range, and can edit them before submitting. Every report belongs to exactly one employee, its owner.
Reports can be archived and restored. Archiving removes old reports from the default view without
destroying their history.

3. **Expense lines.** Every expense line belongs to exactly one report and carries a date, an
amount, a category chosen from a fixed list, and a description. Lines can be added, edited or
removed until the report is submitted. A report's total is always the sum of its lines' amounts,
calculated by the server, never a value the client can set directly.

4. **A report lifecycle with rules.** A report moves through *Draft → Submitted → Approved* or
*Rejected*, and an Approved report is later marked *Paid*. Only the report's owner may submit it,
and only a user with the approver role may approve or reject a submitted report — but the server
never allows an approver to approve or reject a report they own themselves, even though they hold
the role; that report must wait for a different approver. Rejecting a report requires a reason, and
the report then returns to Draft, where its owner can edit it and submit it again. Any other
transition must be rejected by the server with a message explaining why.

5. **Assigned approvers.** Any number of approvers can be assigned to a report as its eligible
approvers, and a single approver can be assigned to any number of reports. Every approver can see
the full queue of submitted reports awaiting a decision, as well as a filtered list of just the
reports assigned to them.

6. **Finding reports.** One list shows expense reports across every employee the viewer can see,
with a text search over the report title, filters for status, owner and approver, sorting by
submitted date, status or total amount, and pagination showing the total number of matches. All of
this must happen on the server — do not load every report into the browser and filter there.

7. **Acting on many reports at once.** An approver can select several submitted reports and
bulk-approve or bulk-reject them in one action. Because the approver may be the owner of one or more
reports in the selection, the server checks every report individually, and the per-report result
names any that were rejected specifically because the approver was also the report's owner,
alongside any other successes or refusals. Separately, export every approved report awaiting payment
— the reimbursements due — as a CSV file.

8. **A dashboard.** A landing view shows headline numbers — reports awaiting approval, total
reimbursements due, reports approved this week, and reports paid this week. It also breaks reports
down by status and by category, and charts total reimbursements paid per week over the last eight
weeks.

9. **History you cannot rewrite.** Every report has a timeline showing every status change with the
old and new status, who made it, and the reason on any rejection, along with any comments left by
the owner or an approver. Nothing in this timeline can be edited or deleted after the fact,
including by approvers.

10. **Stale-approval alerts.** A report that has been sitting in Submitted for more than a set
number of days without a decision appears in an alerts area, with a count badge visible in the
navigation. An approver can dismiss the alert for a report assigned to them. If the report is still
undecided a further set number of days later, the alert returns.

## Stretch ideas (optional)

None of these are required, and none substitute for a goal above. If you finish all ten with time
left over, pick whichever of these sounds most useful and build it:

- Receipt photo attachments with OCR-assisted amount extraction.
- A mileage calculator for vehicle expense lines.
- Multi-currency support with exchange-rate conversion.
- Multi-level approval chains for large amounts.
- Per-category spending limits or policy warnings.
- Corporate card transaction reconciliation.
- A mobile-friendly receipt capture flow.
- Recurring expense templates for regular claims.
- Budget-versus-actual reporting per department.


---

## What we are assessing

A working application is table stakes. Almost every serious candidate will produce something that runs, has a login, and roughly does what was asked. That's the floor, not the differentiator.

What actually separates submissions is the record of thinking behind the app: the decisions you made and why, the trade-offs you weighed, what you built first and what you deliberately left out, and whether you can explain any part of your own system when asked. We are hiring for judgement. The app is the evidence for that judgement, not the deliverable in itself.

We also read the code itself for structure and readability, which counts for a small share of the overall score.

## Time budget

Budget about 12 hours total, spent roughly 2 hours a day across a week.

This is not a race. We are not timing you against other candidates, and submitting early scores nothing extra. Twelve hours is a size guide so you know how much to attempt — pace yourself, stop when you're tired, and spend some of that time thinking and documenting, not only typing code.

## Pick any stack you like

Use any language, any framework, any UI library, any ORM, and any database access approach you want. We have no house stack, and no stack scores better than another — this round is not a test of whether you know particular tools.

Use whatever you are fastest and most confident in. Time spent learning something new to impress us is time not spent on the ten goals above, and it will show.

## Using AI is allowed and encouraged

Use AI tools however you want — to scaffold code, debug a stuck problem, write tests, draft documentation, or anything else that helps you move faster. A few things to know about how we treat it:

- We do not penalise AI use, and we make no attempt to detect it.
- We care about whether you understood, directed and verified the output — not about who or what produced the first draft of it.
- `docs/ai-prompts.md` must contain the prompts you actually used, including the ones that produced bad output and what you changed afterwards. If you used no AI at all, say so here and describe how you worked instead — that is assessed the same way.
- Submitting generated code you cannot explain is the single most common way candidates fail this round.

You are accountable for everything in your submission. If a reviewer points at a piece of code and asks why it's there, or why it works the way it does, "the AI wrote it" is not an answer.

## Use git properly

Publish to a public GitHub repository, and commit incrementally as the work actually happens — after each meaningful step, not in one pass at the end.

A repository whose entire history is a single "initial commit" containing a finished app scores zero on git history, and it colours how we read everything else in your submission, however good the app itself is. Your history is how we see the order you built in, where you got stuck, and how the design changed along the way. If it isn't there, we can't assess it, and we won't assume the best.

## What you must commit

Alongside your code, commit these five files under `docs/`. Your zip includes a stub for each with the questions it needs to answer — fill them in as you go, not from memory at the end.

| File | What it must answer |
|------|----------------------|
| `docs/architecture.md` | What the moving pieces are, how they talk to each other, where each one runs, the request path for one representative user action end to end, and what you decided not to build. |
| `docs/schema.md` | Every table's columns and types, which relationships are one-to-many versus many-to-many, which constraints live in the database versus the application, what you deliberately denormalised, and what would break first at 100x the data. |
| `docs/plan.md` | How you split the work into sessions, what order you built in and why, what you estimated versus what it actually took, and what you cut when you ran short. |
| `docs/decisions.md` | At least five real decisions — what you chose, what you rejected, and why — including at least one you later reversed. |
| `docs/ai-prompts.md` | The prompts you actually used, in order, grouped by what you were trying to do, including at least one that produced something wrong and what you did about it. |

## Host it for free

Deploy the whole thing somewhere reachable by URL, using free tiers only.

One combination that works, if you would rather not decide:

- **Database** — a managed service such as Supabase.
- **Server-side code** — Render.
- **Browser-side code** — Vercel.

Deploy in that order: create the database first, give the server its connection details as environment variables, then point the browser-side part at the server's public URL.

This is one option, not a requirement. Any free host is equally acceptable — everything on a single provider, one virtual machine, a container platform, a static host with serverless functions. The choice earns and loses nothing.

Requirements:

- A working live URL.
- Seeded with enough demo data to show the system doing something, not an empty shell.
- Demo credentials for every role recorded in `SUBMISSION.md`.
- Connection strings, keys and passwords kept in environment variables, never in the repository.
- Free tiers often sleep when idle and can take a minute or more to wake. Note it in `SUBMISSION.md` if yours does, so a slow first load is not read as a broken deployment.
- If you cannot get it hosted, submit anyway and record in `SUBMISSION.md` what you tried and where it broke.

## How to submit

Send us:

- The URL of your public GitHub repository.
- The URL of your live, deployed application.
- Your completed `SUBMISSION.md`, committed to the repository.

That's the whole submission. Nothing else to prepare, no separate form.

## What happens next

If your submission clears the bar, we'll set up a short call. We will ask about specific decisions we can see in your repository and its history — why you modelled something a particular way, what a certain commit was fixing, what you'd change if you kept going.

We're telling you this now because it should change how carefully you document as you go. Write `docs/decisions.md` for a version of yourself who has to explain it three weeks from now.

## Scope

The 10 goals stated in this brief are the cutoff. Meet all 10, solidly, and you have a complete submission.

Stretch ideas are optional. They exist for candidates who finish the 10 with time left and want to keep building — they are never required, and they do not make up for a goal you didn't hit. Doing 8 goals well beats doing 10 goals badly. If time is short, finish fewer goals properly rather than leaving all ten half-done.
