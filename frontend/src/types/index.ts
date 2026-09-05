export type Role = "employee" | "approver"

export type ReportStatus = "draft" | "submitted" | "approved" | "rejected" | "paid"

export type ExpenseCategory = "travel" | "meals" | "lodging" | "supplies" | "software" | "other"

export const EXPENSE_CATEGORIES: ExpenseCategory[] = [
  "travel",
  "meals",
  "lodging",
  "supplies",
  "software",
  "other",
]

export interface User {
  id: number
  email: string
  name: string
  role: Role
}

export interface ExpenseLine {
  id: number
  date: string
  category: ExpenseCategory
  amount_cents: number
  description: string
  other_category_note: string | null
}

// A frozen line as it was at the moment of an approve/reject decision - not a
// real, independently addressable ExpenseLine (no `id`), just a copy of what it
// looked like then. See backend StatusEvent.line_snapshot.
export interface LineSnapshotItem {
  date: string
  category: ExpenseCategory
  amount_cents: number
  description: string
  other_category_note: string | null
}

export interface StatusEvent {
  id: number
  from_status: ReportStatus | null
  to_status: ReportStatus
  actor: User
  reason: string | null
  line_snapshot: LineSnapshotItem[] | null
  created_at: string
}

export interface Comment {
  id: number
  author: User
  body: string
  created_at: string
}

export interface ReportListItem {
  id: number
  title: string
  owner: User
  status: ReportStatus
  total_cents: number
  start_date: string
  end_date: string
  submitted_at: string | null
  archived_at: string | null
  created_at: string
}

export interface ReportListResponse {
  items: ReportListItem[]
  total: number
  page: number
  page_size: number
}

export interface ReportDetail extends ReportListItem {
  lines: ExpenseLine[]
  approvers: User[]
  status_events: StatusEvent[]
  comments: Comment[]
}

export function formatCents(cents: number): string {
  // Pinned to en-US rather than the viewer's own browser locale: this app is
  // USD-only, and leaving the locale undefined would format the same amount
  // differently depending on who's looking (e.g. "1 234,56 $US" instead of
  // "$1,234.56"), which is confusing for a currency the number never changes.
  return (cents / 100).toLocaleString("en-US", { style: "currency", currency: "USD" })
}
