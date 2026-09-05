import { apiFetch, ApiError } from "./client"
import { getToken } from "./authToken"
import type { ExpenseCategory, ExpenseLine, ReportDetail, ReportListResponse, User } from "../types"

const API_BASE = import.meta.env.VITE_API_BASE_URL as string

export interface ReportQuery {
  q?: string
  status?: string
  owner_id?: number
  approver_id?: number
  assigned_to_me?: boolean
  include_archived?: boolean
  sort?: "created_at" | "submitted_at" | "status" | "total_cents"
  sort_dir?: "asc" | "desc"
  page?: number
  page_size?: number
}

export function listReports(query: ReportQuery = {}): Promise<ReportListResponse> {
  return apiFetch<ReportListResponse>("/reports", { params: { ...query } })
}

export function listApprovers(): Promise<User[]> {
  return apiFetch<User[]>("/reports/approvers")
}

/** How many of the current user's own reports are back in Draft specifically
 * because they were rejected - the nav badge for "a rejection needs your
 * attention," since this app sends no email/push notifications at all. */
export function getNeedsAttentionCount(): Promise<{ count: number }> {
  return apiFetch<{ count: number }>("/reports/needs-attention-count")
}

export function setApprovers(reportId: number, approverIds: number[]): Promise<ReportDetail> {
  return apiFetch<ReportDetail>(`/reports/${reportId}/approvers`, {
    method: "PUT",
    body: { approver_ids: approverIds },
  })
}

export function getReport(id: number): Promise<ReportDetail> {
  return apiFetch<ReportDetail>(`/reports/${id}`)
}

export function createReport(data: {
  title: string
  start_date: string
  end_date: string
}): Promise<ReportDetail> {
  return apiFetch<ReportDetail>("/reports", { method: "POST", body: data })
}

export function updateReport(
  id: number,
  data: Partial<{ title: string; start_date: string; end_date: string }>,
): Promise<ReportDetail> {
  return apiFetch<ReportDetail>(`/reports/${id}`, { method: "PATCH", body: data })
}

export function archiveReport(id: number): Promise<ReportDetail> {
  return apiFetch<ReportDetail>(`/reports/${id}/archive`, { method: "POST" })
}

export function restoreReport(id: number): Promise<ReportDetail> {
  return apiFetch<ReportDetail>(`/reports/${id}/restore`, { method: "POST" })
}

export interface LineInput {
  date: string
  category: ExpenseCategory
  amount_cents: number
  description: string
  other_category_note?: string
}

export function addLine(reportId: number, data: LineInput): Promise<ExpenseLine> {
  return apiFetch<ExpenseLine>(`/reports/${reportId}/lines`, { method: "POST", body: data })
}

export function updateLine(reportId: number, lineId: number, data: LineInput): Promise<ExpenseLine> {
  return apiFetch<ExpenseLine>(`/reports/${reportId}/lines/${lineId}`, {
    method: "PATCH",
    body: data,
  })
}

export function deleteLine(reportId: number, lineId: number): Promise<void> {
  return apiFetch<void>(`/reports/${reportId}/lines/${lineId}`, { method: "DELETE" })
}

export function submitReport(id: number): Promise<ReportDetail> {
  return apiFetch<ReportDetail>(`/reports/${id}/submit`, { method: "POST" })
}

export function decideReport(
  id: number,
  decision: "approved" | "rejected",
  reason?: string,
): Promise<ReportDetail> {
  return apiFetch<ReportDetail>(`/reports/${id}/decide`, { method: "POST", body: { decision, reason } })
}

export function payReport(id: number): Promise<ReportDetail> {
  return apiFetch<ReportDetail>(`/reports/${id}/pay`, { method: "POST" })
}

export interface BulkDecideResultItem {
  report_id: number
  ok: boolean
  self_owned: boolean
  reason: string | null
}

export function bulkDecide(
  reportIds: number[],
  decision: "approved" | "rejected",
  reason?: string,
): Promise<{ results: BulkDecideResultItem[] }> {
  return apiFetch<{ results: BulkDecideResultItem[] }>("/reports/bulk-decide", {
    method: "POST",
    body: { report_ids: reportIds, decision, reason },
  })
}

/** CSV download needs the Authorization header, which a plain <a href> can't send -
 * fetch as a blob and trigger the browser's save dialog via a synthetic click. */
export async function downloadExportDueCsv(): Promise<void> {
  const token = getToken()
  const response = await fetch(`${API_BASE}/reports/export-due`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!response.ok) {
    throw new ApiError(response.status, "Failed to export CSV.")
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = "reimbursements_due.csv"
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}
