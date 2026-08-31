from datetime import date

from pydantic import BaseModel


class WeeklyPaid(BaseModel):
    week_start: date
    week_end: date
    total_cents: int


class DashboardResponse(BaseModel):
    awaiting_approval_count: int
    total_due_cents: int
    approved_this_week_count: int
    paid_this_week_count: int
    status_breakdown: dict[str, int]
    category_breakdown: dict[str, int]
    paid_per_week: list[WeeklyPaid]
