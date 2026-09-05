import { useEffect, useState } from "react"
import type { FormEvent } from "react"
import { useNavigate, useParams } from "react-router-dom"
import Layout from "../components/Layout"
import { useAuth } from "../context/AuthContext"
import { ApiError } from "../api/client"
import { addComment } from "../api/comments"
import {
  addLine,
  archiveReport,
  decideReport,
  deleteLine,
  getReport,
  listApprovers,
  payReport,
  restoreReport,
  setApprovers,
  submitReport,
  updateLine,
} from "../api/reports"
import type { ExpenseCategory, ExpenseLine, ReportDetail as ReportDetailType, User } from "../types"
import { EXPENSE_CATEGORIES, formatCents } from "../types"

export default function ReportDetail() {
  const { id } = useParams<{ id: string }>()
  const reportId = Number(id)
  const { user } = useAuth()
  const navigate = useNavigate()

  const [report, setReport] = useState<ReportDetailType | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const [lineDate, setLineDate] = useState("")
  const [lineCategory, setLineCategory] = useState<ExpenseCategory>("travel")
  const [lineAmount, setLineAmount] = useState("")
  const [lineDescription, setLineDescription] = useState("")
  const [lineOtherNote, setLineOtherNote] = useState("")
  // Non-null while the form below is editing an existing line rather than adding
  // a new one - same form serves both, per the existing "Add line" UI, rather
  // than duplicating a second form just for edits.
  const [editingLineId, setEditingLineId] = useState<number | null>(null)

  const [allApprovers, setAllApprovers] = useState<User[] | null>(null)
  const [selectedApproverIds, setSelectedApproverIds] = useState<number[]>([])
  const [commentBody, setCommentBody] = useState("")

  useEffect(() => {
    // Fetched for everyone now, not just approvers - a report's owner can also
    // manage its assignments (routing your own report to whoever should review
    // it), on top of any approver's existing ability to.
    listApprovers().then(setAllApprovers).catch(() => setAllApprovers(null))
  }, [])

  useEffect(() => {
    if (report) setSelectedApproverIds(report.approvers.map((a) => a.id))
  }, [report])

  function reload() {
    getReport(reportId)
      .then(setReport)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load report."))
  }

  useEffect(reload, [reportId])

  async function runAction<T>(action: () => Promise<T>): Promise<boolean> {
    // Every mutating action on this page goes through here, so guarding re-entrancy
    // once here covers all of them - including forms submitted via Enter, which
    // fire regardless of a button's `disabled` state.
    if (busy) return false
    setActionError(null)
    setBusy(true)
    try {
      await action()
      try {
        setReport(await getReport(reportId))
      } catch (reloadErr) {
        if (reloadErr instanceof ApiError && reloadErr.status === 404) {
          // The action itself succeeded - this 404 means it's no longer visible
          // to *us* as a direct, correct result of it (an approver rejecting a
          // report sends it back to Draft, which is invisible to any approver
          // who isn't its owner). That's not a failure to report as a scary
          // error - it's the expected outcome, so just leave for the list
          // instead of showing "Report not found" for something that worked.
          navigate("/reports")
          return true
        }
        throw reloadErr
      }
      return true
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Something went wrong.")
      return false
    } finally {
      setBusy(false)
    }
  }

  function startEditingLine(line: ExpenseLine) {
    setEditingLineId(line.id)
    setLineDate(line.date)
    setLineCategory(line.category)
    setLineAmount((line.amount_cents / 100).toFixed(2))
    setLineDescription(line.description)
    setLineOtherNote(line.other_category_note ?? "")
  }

  function cancelEditingLine() {
    setEditingLineId(null)
    setLineDate("")
    setLineAmount("")
    setLineDescription("")
    setLineOtherNote("")
  }

  async function handleSubmitLine(e: FormEvent) {
    e.preventDefault()
    const cents = Math.round(parseFloat(lineAmount) * 100)
    const payload = {
      date: lineDate,
      category: lineCategory,
      amount_cents: cents,
      description: lineDescription,
      // Only sent when the field is actually shown (category === "other") and
      // filled in - an empty string here would otherwise overwrite nothing into
      // something on the backend, which treats blank the same as omitted anyway,
      // but there's no reason to send it at all for a category where it's unused.
      other_category_note: lineCategory === "other" && lineOtherNote ? lineOtherNote : undefined,
    }
    const ok = await runAction(() =>
      editingLineId ? updateLine(reportId, editingLineId, payload) : addLine(reportId, payload),
    )
    // Only clear the form on success - a rejected line (bad amount, date, etc.)
    // should leave what was typed in place so it isn't silently lost.
    if (ok) {
      setEditingLineId(null)
      setLineDate("")
      setLineAmount("")
      setLineDescription("")
      setLineOtherNote("")
    }
  }

  async function handleAddComment(e: FormEvent) {
    e.preventDefault()
    const body = commentBody
    setCommentBody("")
    const ok = await runAction(() => addComment(reportId, body))
    // Cleared optimistically above for a snappy feel; restore it if it actually failed.
    if (!ok) setCommentBody(body)
  }

  if (error) return <Layout><p className="form-error">{error}</p></Layout>
  if (!report) return <Layout><p>Loading...</p></Layout>

  const isOwner = user?.id === report.owner.id
  const isApprover = user?.role === "approver"
  const canEditLines = isOwner && report.status === "draft"
  const canSubmit = isOwner && report.status === "draft"
  const canDecide = isApprover && !isOwner && report.status === "submitted"
  const canMarkPaid = isApprover && !isOwner && report.status === "approved"
  const canArchive = isOwner && !report.archived_at
  const canRestore = isOwner && !!report.archived_at

  const currentApproverIds = new Set(report.approvers.map((a) => a.id))
  const approverSelectionChanged =
    currentApproverIds.size !== selectedApproverIds.length ||
    selectedApproverIds.some((id) => !currentApproverIds.has(id))

  const timeline = [
    ...report.status_events.map((e) => ({
      kind: "status" as const,
      created_at: e.created_at,
      node: (
        <span>
          <strong>{e.actor.name}</strong>: {e.from_status ?? "(new)"} &rarr; {e.to_status}
          {e.reason && <em> - "{e.reason}"</em>}
        </span>
      ),
    })),
    ...report.comments.map((c) => ({
      kind: "comment" as const,
      created_at: c.created_at,
      node: (
        <span>
          <strong>{c.author.name}</strong> commented: {c.body}
        </span>
      ),
    })),
  ].sort((a, b) => a.created_at.localeCompare(b.created_at))

  return (
    <Layout>
      <div className="page-header">
        <h1>
          {report.title} <span className={`status-badge status-${report.status}`}>{report.status}</span>
        </h1>
      </div>
      <p>
        Owner: {report.owner.name} &middot; {report.start_date} to {report.end_date} &middot; Total:{" "}
        {formatCents(report.total_cents)}
      </p>
      {report.archived_at && <p className="badge">Archived</p>}

      {actionError && <p className="form-error">{actionError}</p>}

      <section>
        <h2>Assigned approvers</h2>
        {(isApprover || isOwner) && allApprovers ? (
          <>
            <div className="approver-picker">
              {allApprovers.map((a) => (
                <label key={a.id} className="inline-checkbox">
                  <input
                    type="checkbox"
                    checked={selectedApproverIds.includes(a.id)}
                    onChange={(e) => {
                      setSelectedApproverIds((prev) =>
                        e.target.checked ? [...prev, a.id] : prev.filter((id) => id !== a.id),
                      )
                    }}
                  />
                  {a.name}
                </label>
              ))}
            </div>
            <button
              className="btn-primary btn-sm"
              disabled={busy || !approverSelectionChanged}
              onClick={() => runAction(() => setApprovers(reportId, selectedApproverIds))}
            >
              Save assignments
            </button>
          </>
        ) : (
          <p>
            {report.approvers.length > 0
              ? report.approvers.map((a) => a.name).join(", ")
              : "None assigned yet."}
          </p>
        )}
      </section>

      <section>
        <h2>Lines</h2>
        <table className="data-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Category</th>
              <th>Description</th>
              <th>Amount</th>
              {canEditLines && <th />}
            </tr>
          </thead>
          <tbody>
            {report.lines.map((line) => (
              <tr key={line.id}>
                <td>{line.date}</td>
                <td>
                  {line.category === "other" && line.other_category_note ? (
                    // Show what they actually specified instead of the generic
                    // "other" - the hover title keeps the real category visible
                    // without cluttering the cell with both.
                    <span title="Category: Other">{line.other_category_note}</span>
                  ) : (
                    line.category
                  )}
                </td>
                <td>{line.description}</td>
                <td>{formatCents(line.amount_cents)}</td>
                {canEditLines && (
                  <td className="action-bar">
                    <button className="btn-ghost btn-sm" disabled={busy} onClick={() => startEditingLine(line)}>
                      Edit
                    </button>
                    <button
                      className="btn-danger btn-sm"
                      disabled={busy}
                      onClick={async () => {
                        const ok = await runAction(() => deleteLine(reportId, line.id))
                        // The line being edited no longer exists - don't leave the
                        // form sitting there pointed at a now-deleted line.
                        if (ok && editingLineId === line.id) cancelEditingLine()
                      }}
                    >
                      Remove
                    </button>
                  </td>
                )}
              </tr>
            ))}
            {report.lines.length === 0 && (
              <tr>
                <td colSpan={5}>No lines yet.</td>
              </tr>
            )}
          </tbody>
        </table>

        {canEditLines && (
          <form onSubmit={handleSubmitLine} className="inline-form">
            <input type="date" value={lineDate} onChange={(e) => setLineDate(e.target.value)} required />
            <select
              value={lineCategory}
              onChange={(e) => {
                const next = e.target.value as ExpenseCategory
                setLineCategory(next)
                // No reason to keep a hidden, stale note around once the field
                // that shows it is gone.
                if (next !== "other") setLineOtherNote("")
              }}
            >
              {EXPENSE_CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            <input
              placeholder="Description"
              value={lineDescription}
              onChange={(e) => setLineDescription(e.target.value)}
              required
            />
            {lineCategory === "other" && (
              <input
                placeholder="Specify (optional)"
                value={lineOtherNote}
                onChange={(e) => setLineOtherNote(e.target.value)}
              />
            )}
            <input
              type="number"
              step="0.01"
              min="0.01"
              placeholder="Amount"
              value={lineAmount}
              onChange={(e) => setLineAmount(e.target.value)}
              required
            />
            <button type="submit" className="btn-primary" disabled={busy}>
              {editingLineId ? "Save changes" : "Add line"}
            </button>
            {editingLineId && (
              <button type="button" className="btn-ghost" disabled={busy} onClick={cancelEditingLine}>
                Cancel
              </button>
            )}
          </form>
        )}
      </section>

      <section className="action-bar">
        {canSubmit && (
          <button className="btn-primary" disabled={busy} onClick={() => runAction(() => submitReport(reportId))}>
            Submit
          </button>
        )}
        {canDecide && (
          <>
            <button
              className="btn-primary"
              disabled={busy}
              onClick={() => runAction(() => decideReport(reportId, "approved"))}
            >
              Approve
            </button>
            <button
              className="btn-danger"
              disabled={busy}
              onClick={() => {
                const reason = window.prompt("Reason for rejecting this report?")
                if (reason && reason.trim()) {
                  runAction(() => decideReport(reportId, "rejected", reason.trim()))
                }
              }}
            >
              Reject
            </button>
          </>
        )}
        {canMarkPaid && (
          <button className="btn-primary" disabled={busy} onClick={() => runAction(() => payReport(reportId))}>
            Mark as paid
          </button>
        )}
        {canArchive && (
          <button className="btn-ghost" disabled={busy} onClick={() => runAction(() => archiveReport(reportId))}>
            Archive
          </button>
        )}
        {canRestore && (
          <button className="btn-ghost" disabled={busy} onClick={() => runAction(() => restoreReport(reportId))}>
            Restore
          </button>
        )}
      </section>

      <section>
        <h2>Timeline</h2>
        {timeline.length === 0 && <p>No history yet.</p>}
        <ul className="timeline">
          {timeline.map((item, i) => (
            <li key={i}>
              <time>{new Date(item.created_at).toLocaleString()}</time> {item.node}
            </li>
          ))}
        </ul>
        <form onSubmit={handleAddComment} className="inline-form">
          <input
            placeholder="Add a comment..."
            value={commentBody}
            onChange={(e) => setCommentBody(e.target.value)}
            required
          />
          <button type="submit" className="btn-primary" disabled={busy}>
            Comment
          </button>
        </form>
      </section>
    </Layout>
  )
}
