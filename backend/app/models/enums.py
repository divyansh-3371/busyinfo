"""Shared enum types. Fixed lists per the assignment brief — see docs/decisions.md for
why the category list has these exact six values (the brief doesn't specify one)."""
import enum


class Role(str, enum.Enum):
    employee = "employee"
    approver = "approver"


class ReportStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"
    paid = "paid"


class ExpenseCategory(str, enum.Enum):
    travel = "travel"
    meals = "meals"
    lodging = "lodging"
    supplies = "supplies"
    software = "software"
    other = "other"
