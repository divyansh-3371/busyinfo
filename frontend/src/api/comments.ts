import { apiFetch } from "./client"
import type { Comment } from "../types"

export function addComment(reportId: number, body: string): Promise<Comment> {
  return apiFetch<Comment>(`/reports/${reportId}/comments`, { method: "POST", body: { body } })
}
