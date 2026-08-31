import { apiFetch } from "./client"
import type { ExpenseCategory, ExpenseLine, ReportDetail, ReportListResponse, User } from "../types"

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
