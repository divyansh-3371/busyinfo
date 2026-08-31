import { apiFetch } from "./client"

export interface WeeklyPaid {
  week_start: string
  week_end: string
  total_cents: number
}

export interface DashboardData {
  awaiting_approval_count: number
  total_due_cents: number
  approved_this_week_count: number
  paid_this_week_count: number
  status_breakdown: Record<string, number>
  category_breakdown: Record<string, number>
  paid_per_week: WeeklyPaid[]
}

export function getDashboard(): Promise<DashboardData> {
  return apiFetch<DashboardData>("/dashboard")
}
