from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.models.enums import ExpenseCategory, ReportStatus
from app.schemas.user import UserOut

MAX_AMOUNT_CENTS = 100_000_000  # $1,000,000 - a sanity bound, not a policy limit
MAX_TITLE_LENGTH = 255
MAX_DESCRIPTION_LENGTH = 2000


class ExpenseLineIn(BaseModel):
    date: date
    category: ExpenseCategory
    amount_cents: int
    description: str
    # Optional elaboration, meant for when category="other" but not restricted to
    # it at this layer - the frontend only shows the field for "Other", but there's
    # no reason to reject it if a client sends one alongside a different category.
    # Unlike description, blank/missing is fine - never validated as required.
    other_category_note: str | None = None

    @field_validator("amount_cents")
    @classmethod
    def amount_in_range(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Amount must be greater than zero.")
        if v > MAX_AMOUNT_CENTS:
            raise ValueError("Amount is unreasonably large.")
        return v

    @field_validator("description")
    @classmethod
    def description_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Description cannot be blank.")
        if len(v) > MAX_DESCRIPTION_LENGTH:
            raise ValueError(f"Description cannot exceed {MAX_DESCRIPTION_LENGTH} characters.")
        return v

    @field_validator("other_category_note")
    @classmethod
    def other_category_note_optional(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None  # whitespace-only counts as "didn't fill it in", not an empty note
        if len(v) > MAX_DESCRIPTION_LENGTH:
            raise ValueError(f"Note cannot exceed {MAX_DESCRIPTION_LENGTH} characters.")
        return v


class ExpenseLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: date
    category: ExpenseCategory
    amount_cents: int
    description: str
    other_category_note: str | None


class ReportCreate(BaseModel):
    title: str
    start_date: date
    end_date: date

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Title cannot be blank.")
        if len(v) > MAX_TITLE_LENGTH:
            raise ValueError(f"Title cannot exceed {MAX_TITLE_LENGTH} characters.")
        return v

    @model_validator(mode="after")
    def dates_ordered(self):
        if self.end_date < self.start_date:
            raise ValueError("End date cannot be before start date.")
        return self


class ReportUpdate(BaseModel):
    title: str | None = None
    start_date: date | None = None
    end_date: date | None = None

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("Title cannot be blank.")
        if len(v) > MAX_TITLE_LENGTH:
            raise ValueError(f"Title cannot exceed {MAX_TITLE_LENGTH} characters.")
        return v


class LineSnapshotItem(BaseModel):
    """One frozen line as it was at the moment of an approve/reject decision - see
    StatusEvent.line_snapshot. Deliberately has no `id`: these aren't real,
    independently addressable ExpenseLine rows, just a frozen copy of what they
    looked like at the time."""

    date: date
    category: ExpenseCategory
    amount_cents: int
    description: str
    other_category_note: str | None = None


class StatusEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    from_status: ReportStatus | None
    to_status: ReportStatus
    actor: UserOut
    reason: str | None
    line_snapshot: list[LineSnapshotItem] | None
    created_at: datetime


class CommentCreate(BaseModel):
    body: str

    @field_validator("body")
    @classmethod
    def body_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Comment cannot be blank.")
        if len(v) > MAX_DESCRIPTION_LENGTH:
            raise ValueError(f"Comment cannot exceed {MAX_DESCRIPTION_LENGTH} characters.")
        return v


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    author: UserOut
    body: str
    created_at: datetime


class ReportListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    owner: UserOut
    status: ReportStatus
    total_cents: int
    start_date: date
    end_date: date
    submitted_at: datetime | None
    archived_at: datetime | None
    needs_owner_attention: bool
    created_at: datetime


class ReportDetail(ReportListItem):
    lines: list[ExpenseLineOut]
    approvers: list[UserOut]
    status_events: list[StatusEventOut]
    comments: list[CommentOut]


class ReportListResponse(BaseModel):
    items: list[ReportListItem]
    total: int
    page: int
    page_size: int


class NeedsAttentionCount(BaseModel):
    count: int


class DecideRequest(BaseModel):
    decision: str  # "approved" | "rejected" - validated in the route against the enum
    reason: str | None = None


class AssignApproversRequest(BaseModel):
    approver_ids: list[int]


class BulkDecideRequest(BaseModel):
    report_ids: list[int]
    decision: str  # "approved" | "rejected"
    reason: str | None = None


class BulkDecideResultItem(BaseModel):
    report_id: int
    ok: bool
    self_owned: bool = False  # True specifically when this one failed because the
    # acting approver owns it - goal 7 requires this be distinguishable from other
    # failures, not just present in the reason text.
    reason: str | None = None  # populated only when ok is False


class BulkDecideResponse(BaseModel):
    results: list[BulkDecideResultItem]
