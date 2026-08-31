# Schema

All tables live in one Postgres database, defined in `backend/app/models/*.py` and
reaching the database through `backend/alembic/versions/`. Money is stored as
integer cents (`amount_cents`, `total_cents`) to avoid floating-point rounding.

## Tables

### `users`
| Column | Type | Notes |
|---|---|---|
| `id` | `serial` PK | |
| `email` | `varchar(255)` | unique, indexed |
| `password_hash` | `varchar(255)` | bcrypt |
| `name` | `varchar(255)` | |
| `role` | `enum('employee','approver')` | |
| `created_at` | `timestamp` | server default `now()` |

### `expense_reports`
| Column | Type | Notes |
|---|---|---|
| `id` | `serial` PK | |
| `owner_id` | `int` FK → `users.id` | |
| `title` | `varchar(255)` | |
| `start_date`, `end_date` | `date` | |
| `status` | `enum('draft','submitted','approved','rejected','paid')` | indexed |
| `total_cents` | `bigint` | **denormalized** — see below |
| `submitted_at` | `timestamp`, nullable | **denormalized** — see below |
| `archived_at` | `timestamp`, nullable | indexed; `NULL` = not archived |
| `created_at`, `updated_at` | `timestamp` | |

### `expense_lines`
| Column | Type | Notes |
|---|---|---|
| `id` | `serial` PK | |
| `report_id` | `int` FK → `expense_reports.id`, `ON DELETE CASCADE` | indexed |
| `date` | `date` | |
| `amount_cents` | `bigint` | app-validated `> 0`, capped at $1,000,000 |
| `category` | `enum('travel','meals','lodging','supplies','software','other')` | fixed list, not in the brief — our choice |
| `description` | `text` | app-validated non-blank |
| `created_at` | `timestamp` | |

### `report_approvers` (join table)
| Column | Type | Notes |
|---|---|---|
| `report_id` | `int` FK → `expense_reports.id`, `ON DELETE CASCADE` | composite PK |
| `approver_id` | `int` FK → `users.id` | composite PK, also indexed alone |
| `created_at` | `timestamp` | |

The composite primary key `(report_id, approver_id)` is what makes assigning the
same approver twice idempotent — a second insert of the same pair is a constraint
violation the app already guards against by deduplicating before writing.

### `status_events` (append-only audit trail)
| Column | Type | Notes |
|---|---|---|
| `id` | `serial` PK | |
| `report_id` | `int` FK → `expense_reports.id`, `ON DELETE CASCADE` | indexed |
| `from_status` | `enum(report_status)`, nullable | |
| `to_status` | `enum(report_status)` | |
| `actor_id` | `int` FK → `users.id` | |
| `reason` | `text`, nullable | required by a **DB-level `CHECK`** when `to_status = 'rejected'` |
| `created_at` | `timestamp` | |

### `comments` (append-only)
| Column | Type | Notes |
|---|---|---|
| `id` | `serial` PK | |
| `report_id` | `int` FK → `expense_reports.id`, `ON DELETE CASCADE` | indexed |
| `author_id` | `int` FK → `users.id` | |
| `body` | `text` | app-validated non-blank |
| `created_at` | `timestamp` | |

### `alert_dismissals`
| Column | Type | Notes |
|---|---|---|
| `id` | `serial` PK | |
| `report_id` | `int` FK → `expense_reports.id`, `ON DELETE CASCADE` | indexed |
| `approver_id` | `int` FK → `users.id` | |
| `dismissed_at` | `timestamp` | |
| `snoozed_until` | `timestamp` | when the alert is allowed to reappear |

`UNIQUE(report_id, approver_id)` — one active dismissal per approver per report;
re-dismissing updates the existing row (`dismissed_at`/`snoozed_until`) rather than
inserting a second one.

## Relationships

| Relationship | Cardinality |
|---|---|
| `users` → `expense_reports` (owner) | one-to-many |
| `expense_reports` → `expense_lines` | one-to-many |
| `expense_reports` ↔ `users` (approvers) | **many-to-many**, via `report_approvers` |
| `expense_reports` → `status_events` | one-to-many |
| `expense_reports` → `comments` | one-to-many |
| `expense_reports` ↔ `users` (dismissals) | many-to-many in shape, via `alert_dismissals`, but used as one-row-per-pair, not a general association |

## Constraints: database vs. application

**Enforced by the database:**
- Every foreign key (referential integrity — you cannot insert a line for a
  nonexistent report).
- `ON DELETE CASCADE` on every child of `expense_reports` (deleting a report — not
  that this app ever actually exposes a hard-delete route — takes its lines,
  approver links, history, and comments with it; archiving, the actual "remove
  without destroying," never triggers this).
- Uniqueness: `users.email`, `report_approvers(report_id, approver_id)`,
  `alert_dismissals(report_id, approver_id)`.
- One real business rule, deliberately: `status_events` has a `CHECK` constraint
  that `to_status != 'rejected' OR reason IS NOT NULL`. This is the one place we
  chose to enforce a domain rule at the database layer instead of only in
  `services/report_rules.py`, specifically because it's cheap, it's exactly the kind
  of rule a reviewer might ask "what stops someone from writing a bad row directly,"
  and it costs nothing to add.

**Enforced only by the application** (everywhere else): the entire lifecycle
transition table, the self-approval block, amount bounds, title/description
length caps, category validity beyond the enum type itself, and — critically — the
append-only-ness of `status_events`/`comments`. We drew the line here because
duplicating the full transition table as a database trigger or stored procedure
would cost real time for a 2-day project and gains little: the application is the
only thing that ever writes to this database, so an application-level guarantee is
already a real guarantee for this system's actual threat model. It would not be
enough for a system where multiple independent applications wrote to the same
database, or where a hostile actor might have direct SQL access — that's the
honest limit of this choice.

## What was deliberately denormalized

`expense_reports.total_cents` and `expense_reports.submitted_at` are both
denormalized: `total_cents` could always be computed as `SUM(expense_lines.amount_cents)
WHERE report_id = ...`, and `submitted_at` could always be read off the most recent
`status_events` row where `to_status = 'submitted'`. Both are instead cached columns,
recomputed by `services/report_rules.py` whenever they'd change (`recalculate_total`
on every line mutation; `submit()` sets `submitted_at` on the Draft→Submitted
transition). The reason in both cases is the same: goal 6 requires server-side
sorting by total amount and by submitted date, and a cached, indexed column turns
that into a plain `ORDER BY` instead of a join or correlated subquery on every single
list request — which matters because that same query also has to do search,
multiple filters, and pagination in one pass.

The trade-off, made explicit: if `recalculate_total` or `submit()` were ever called
inconsistently, or a report's lines were ever changed through a path that skipped
that function, `total_cents` could drift from the truth. There's no route that
mutates lines without going through the service function, and no test currently
proves that invariant holds under concurrent writes — that's the honest gap.

## What would break first at 100x the data

At roughly current data volumes this schema is fine; at 100x (hundreds of thousands
of reports), the first things to actually hurt:

1. **The category breakdown and dashboard aggregates** (`services/dashboard.py`) run
   several full aggregate queries over `expense_lines`/`status_events` on every
   dashboard load, with no caching. These would need either materialized views, a
   scheduled rollup table, or at minimum a much narrower default time window.
2. **CSV export** (`GET /reports/export-due`) builds the entire CSV in memory in one
   request. Fine for "however many approved-and-unpaid reports exist right now";
   not fine if that number is ever large — it would need real streaming (yielding
   rows as they're fetched, not building the whole `StringIO` first) or pagination.
3. **The title search** (`ILIKE '%...%'`) can't use a standard b-tree index for a
   leading wildcard — at 100x the data this table scan gets slow. A `pg_trgm` GIN
   index (or moving search to a dedicated search engine) would be the real fix.
4. **`status_events`/`comments` growing without bound** — they're append-only by
   design, so a very old, very active report could accumulate a long history. Not a
   correctness problem, but a "the timeline view loads every row, unpaginated"
   performance problem eventually.
