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
}

export interface StatusEvent {
  id: number
  from_status: ReportStatus | null
  to_status: ReportStatus
  actor: User
  reason: string | null
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
  return (cents / 100).toLocaleString(undefined, { style: "currency", currency: "USD" })
}
