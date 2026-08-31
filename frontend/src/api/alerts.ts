import { apiFetch } from "./client"
import type { ReportDetail, ReportListItem } from "../types"

export function listAlerts(): Promise<ReportListItem[]> {
  return apiFetch<ReportListItem[]>("/alerts")
}

export function dismissAlert(reportId: number): Promise<ReportDetail> {
  return apiFetch<ReportDetail>(`/alerts/${reportId}/dismiss`, { method: "POST" })
}
