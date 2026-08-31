"""Wipes and reseeds the database with demo data. Safe to run against a fresh DB or
re-run against one that already has this seed's data in it.

Deliberately bypasses the future report_rules service layer and writes StatusEvent
rows directly - this is seed data standing in for a history that "already happened,"
not a simulation of a user clicking through the app. Amounts are USD cents.

Run: python seed.py   (from the backend/ directory, with DATABASE_URL pointing at the
target database)
"""
from datetime import date, datetime, timedelta, timezone

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.alert import AlertDismissal
from app.models.approver import ReportApprover
from app.models.comment import Comment
from app.models.enums import ExpenseCategory, ReportStatus, Role
from app.models.line import ExpenseLine
from app.models.report import ExpenseReport
from app.models.status_event import StatusEvent
from app.models.user import User

DEMO_PASSWORD = "password123"
NOW = datetime.now(timezone.utc)


def days_ago(n: int) -> datetime:
    return NOW - timedelta(days=n)


def wipe(db):
    # Children first, respecting FKs (models also cascade on delete, but being
    # explicit here makes the wipe order legible).
    for model in [AlertDismissal, Comment, StatusEvent, ExpenseLine, ReportApprover, ExpenseReport, User]:
        db.query(model).delete()
    db.commit()


def make_user(db, email: str, name: str, role: Role) -> User:
    user = User(email=email, name=name, role=role, password_hash=hash_password(DEMO_PASSWORD))
    db.add(user)
    db.flush()
    return user


def make_report(
    db,
    *,
    owner: User,
    title: str,
    start: date,
    end: date,
    lines: list[tuple[date, str, int, str]],  # (date, category, amount_cents, description)
    approvers: list[User] | None = None,
    status_history: list[tuple[ReportStatus | None, ReportStatus, User, str | None, datetime]] = (),
    comments: list[tuple[User, str, datetime]] = (),
    archived_at: datetime | None = None,
    created_at: datetime | None = None,
) -> ExpenseReport:
    submitted_at = next(
        (when for _, to_status, _, _, when in status_history if to_status == ReportStatus.submitted),
        None,
    )
    report = ExpenseReport(
        owner_id=owner.id,
        title=title,
        start_date=start,
        end_date=end,
        status=status_history[-1][1] if status_history else ReportStatus.draft,
        submitted_at=submitted_at,
        archived_at=archived_at,
        created_at=created_at or NOW,
    )
    db.add(report)
    db.flush()

    total = 0
    for line_date, category, amount_cents, description in lines:
        db.add(
            ExpenseLine(
                report_id=report.id,
                date=line_date,
                category=ExpenseCategory(category),
                amount_cents=amount_cents,
                description=description,
            )
        )
        total += amount_cents
    report.total_cents = total

    for approver in approvers or []:
        db.add(ReportApprover(report_id=report.id, approver_id=approver.id))

    for from_status, to_status, actor, reason, when in status_history:
        db.add(
            StatusEvent(
                report_id=report.id,
                from_status=from_status,
                to_status=to_status,
                actor_id=actor.id,
                reason=reason,
                created_at=when,
            )
        )

    for author, body, when in comments:
        db.add(Comment(report_id=report.id, author_id=author.id, body=body, created_at=when))

    return report


def main():
    db = SessionLocal()
    try:
        wipe(db)

        alice = make_user(db, "alice@example.com", "Alice Nguyen", Role.employee)
        bob = make_user(db, "bob@example.com", "Bob Martinez", Role.employee)
        carol = make_user(db, "carol@example.com", "Carol Osei", Role.approver)
        dave = make_user(db, "dave@example.com", "Dave Kim", Role.approver)
        db.flush()

        # --- Draft: untouched, no approvers assigned yet ---
        make_report(
            db,
            owner=alice,
            title="Client site visit - Chicago",
            start=date.today() - timedelta(days=5),
            end=date.today() - timedelta(days=3),
            lines=[
                (date.today() - timedelta(days=5), "travel", 32000, "Flight to Chicago"),
                (date.today() - timedelta(days=4), "meals", 4500, "Dinner with client"),
            ],
        )

        # --- Submitted, not yet stale (2 days < STALE_ALERT_DAYS default of 3) ---
        make_report(
            db,
            owner=alice,
            title="Q2 conference",
            start=date.today() - timedelta(days=10),
            end=date.today() - timedelta(days=7),
            lines=[
                (date.today() - timedelta(days=10), "travel", 45000, "Conference airfare"),
                (date.today() - timedelta(days=9), "lodging", 60000, "Hotel, 3 nights"),
                (date.today() - timedelta(days=8), "meals", 8200, "Meals during conference"),
            ],
            approvers=[carol, dave],
            status_history=[(ReportStatus.draft, ReportStatus.submitted, alice, None, days_ago(2))],
            created_at=days_ago(4),
        )

        # --- Submitted, stale (5 days > 3-day threshold) - shows in alerts, no dismissal ---
        make_report(
            db,
            owner=alice,
            title="Team offsite supplies",
            start=date.today() - timedelta(days=14),
            end=date.today() - timedelta(days=14),
            lines=[(date.today() - timedelta(days=14), "supplies", 15000, "Whiteboards and markers")],
            approvers=[carol],
            status_history=[(ReportStatus.draft, ReportStatus.submitted, alice, None, days_ago(5))],
            created_at=days_ago(6),
        )

        # --- Stale, WAS dismissed, but the snooze already expired - alert reappears ---
        make_report(
            db,
            owner=alice,
            title="Recruiting dinner",
            start=date.today() - timedelta(days=9),
            end=date.today() - timedelta(days=9),
            lines=[(date.today() - timedelta(days=9), "meals", 9800, "Candidate dinner")],
            approvers=[dave],
            status_history=[(ReportStatus.draft, ReportStatus.submitted, alice, None, days_ago(6))],
            created_at=days_ago(7),
        )

        # --- Approved, not yet paid (shows in "reimbursements due") ---
        r_due = make_report(
            db,
            owner=bob,
            title="Design tool subscription",
            start=date.today() - timedelta(days=10),
            end=date.today() - timedelta(days=10),
            lines=[(date.today() - timedelta(days=10), "software", 2900, "Monthly design tool seat")],
            approvers=[carol, dave],
            status_history=[
                (ReportStatus.draft, ReportStatus.submitted, bob, None, days_ago(9)),
                (ReportStatus.submitted, ReportStatus.approved, carol, None, days_ago(8)),
            ],
            comments=[(carol, "Approved - within the monthly software allowance.", days_ago(8))],
            created_at=days_ago(10),
        )

        # --- Rejected, back in Draft (owner can edit and resubmit) ---
        make_report(
            db,
            owner=bob,
            title="Client dinner - downtown",
            start=date.today() - timedelta(days=12),
            end=date.today() - timedelta(days=12),
            lines=[
                (date.today() - timedelta(days=12), "meals", 21000, "Dinner, 4 attendees"),
                (date.today() - timedelta(days=12), "travel", 3500, "Parking"),
            ],
            approvers=[dave],
            status_history=[
                (ReportStatus.draft, ReportStatus.submitted, bob, None, days_ago(11)),
                (
                    ReportStatus.submitted,
                    ReportStatus.rejected,
                    dave,
                    "Missing an itemized receipt for the meal - please attach and resubmit.",
                    days_ago(10),
                ),
                # Automatic follow-on of the same reject action (see
                # services/report_rules.decide) - same actor, no separate reason.
                (ReportStatus.rejected, ReportStatus.draft, dave, None, days_ago(10)),
            ],
            created_at=days_ago(12),
        )

        # --- Owned by an approver, assigned to herself -> demonstrates the self-approval
        # block: Carol cannot decide on this even though she is both the approver role
        # AND explicitly assigned. Only Dave can act on it. ---
        make_report(
            db,
            owner=carol,
            title="Carol's own travel claim",
            start=date.today() - timedelta(days=2),
            end=date.today() - timedelta(days=1),
            lines=[(date.today() - timedelta(days=2), "travel", 27500, "Client visit - own expense")],
            approvers=[carol, dave],
            status_history=[(ReportStatus.draft, ReportStatus.submitted, carol, None, days_ago(1))],
            comments=[
                (dave, "Picking this one up since Carol owns it and can't self-approve.", days_ago(1))
            ],
            created_at=days_ago(2),
        )

        # --- Archived (paid, then archived - still in history, out of the default view) ---
        make_report(
            db,
            owner=bob,
            title="Old onboarding travel (archived)",
            start=date.today() - timedelta(days=70),
            end=date.today() - timedelta(days=68),
            lines=[(date.today() - timedelta(days=70), "travel", 55000, "Relocation flight")],
            approvers=[carol],
            status_history=[
                (ReportStatus.draft, ReportStatus.submitted, bob, None, days_ago(69)),
                (ReportStatus.submitted, ReportStatus.approved, carol, None, days_ago(67)),
                (ReportStatus.approved, ReportStatus.paid, carol, None, days_ago(65)),
            ],
            archived_at=days_ago(60),
            created_at=days_ago(70),
        )

        # --- 8 weeks of paid history so the dashboard's weekly chart has real shape ---
        owners = [alice, bob]
        approver_cycle = [carol, dave]
        categories = ["travel", "meals", "lodging", "supplies", "software", "other"]
        for week in range(1, 9):
            owner = owners[week % 2]
            approver = approver_cycle[week % 2]
            paid_at = days_ago(week * 7)
            submitted_at = paid_at - timedelta(days=4)
            approved_at = paid_at - timedelta(days=2)
            amount = 8000 + (week * 1500)
            make_report(
                db,
                owner=owner,
                title=f"Recurring travel claim - week -{week}",
                start=(paid_at - timedelta(days=6)).date(),
                end=(paid_at - timedelta(days=4)).date(),
                lines=[((paid_at - timedelta(days=5)).date(), categories[week % len(categories)], amount, "Routine expense")],
                approvers=[approver],
                status_history=[
                    (ReportStatus.draft, ReportStatus.submitted, owner, None, submitted_at),
                    (ReportStatus.submitted, ReportStatus.approved, approver, None, approved_at),
                    (ReportStatus.approved, ReportStatus.paid, approver, None, paid_at),
                ],
                created_at=submitted_at - timedelta(days=1),
            )

        db.commit()

        # Dismiss the "Recruiting dinner" alert, but with an already-expired snooze -
        # demonstrates goal 10's "reappears after N more days" behavior without waiting.
        recruiting_dinner = (
            db.query(ExpenseReport).filter(ExpenseReport.title == "Recruiting dinner").one()
        )
        db.add(
            AlertDismissal(
                report_id=recruiting_dinner.id,
                approver_id=dave.id,
                dismissed_at=days_ago(5),
                snoozed_until=days_ago(1),  # already in the past relative to "now"
            )
        )
        db.commit()

        print("Seed complete.")
        print(f"  Users: alice/bob (employee), carol/dave (approver) - password '{DEMO_PASSWORD}' for all")
        print(f"  Reports: {db.query(ExpenseReport).count()}")
        print(f"  Approved-and-unpaid demo report id: {r_due.id}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
