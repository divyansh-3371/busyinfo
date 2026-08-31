import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import Layout from "../components/Layout"
import { useAuth } from "../context/AuthContext"
import { bulkDecide, downloadExportDueCsv, listReports } from "../api/reports"
import type { BulkDecideResultItem } from "../api/reports"
import { ApiError } from "../api/client"
import type { ReportListResponse } from "../types"
import { formatCents } from "../types"

const PAGE_SIZE = 10
const STATUSES = ["draft", "submitted", "approved", "rejected", "paid"] as const

export default function ReportsList() {
  const { user } = useAuth()
  const [data, setData] = useState<ReportListResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [q, setQ] = useState("")
  const [status, setStatus] = useState("")
  const [includeArchived, setIncludeArchived] = useState(false)
  const [assignedToMe, setAssignedToMe] = useState(false)
  const [sort, setSort] = useState<"created_at" | "submitted_at" | "status" | "total_cents">(
    "created_at",
  )
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc")
  const [page, setPage] = useState(1)

  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [bulkResults, setBulkResults] = useState<BulkDecideResultItem[] | null>(null)
  const [bulkError, setBulkError] = useState<string | null>(null)
  const [bulkBusy, setBulkBusy] = useState(false)

  function reload() {
    setError(null)
    listReports({
      q: q || undefined,
      status: status || undefined,
      include_archived: includeArchived,
      assigned_to_me: assignedToMe,
      sort,
      sort_dir: sortDir,
      page,
      page_size: PAGE_SIZE,
    })
      .then((res) => {
        setData(res)
        setSelectedIds((prev) => prev.filter((id) => res.items.some((item) => item.id === id)))
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load reports."))
  }

  useEffect(() => {
    setData(null)
    reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, status, includeArchived, assignedToMe, sort, sortDir, page])

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1
  const selectableIds = data ? data.items.filter((r) => r.status === "submitted").map((r) => r.id) : []

  async function handleBulk(decision: "approved" | "rejected") {
    let reason: string | undefined
    if (decision === "rejected") {
      const entered = window.prompt("Reason for rejecting these reports?")
      if (!entered || !entered.trim()) return
      reason = entered.trim()
    }
    setBulkError(null)
    setBulkResults(null)
    setBulkBusy(true)
    try {
      const { results } = await bulkDecide(selectedIds, decision, reason)
      setBulkResults(results)
      setSelectedIds([])
      reload()
    } catch (err) {
      setBulkError(err instanceof ApiError ? err.message : "Bulk action failed.")
    } finally {
      setBulkBusy(false)
    }
  }

  return (
    <Layout>
      <div className="page-header">
        <h1>Reports</h1>
        {user?.role === "approver" && (
          <button
            onClick={() =>
              downloadExportDueCsv().catch((err) =>
                setBulkError(err instanceof ApiError ? err.message : "Export failed."),
              )
            }
          >
            Export reimbursements due (CSV)
          </button>
        )}
      </div>

      <div className="filter-bar">
        <input
          placeholder="Search title..."
          value={q}
          onChange={(e) => {
            setPage(1)
            setQ(e.target.value)
          }}
        />
        <select
          value={status}
          onChange={(e) => {
            setPage(1)
            setStatus(e.target.value)
          }}
        >
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as typeof sort)}
        >
          <option value="created_at">Sort: created</option>
          <option value="submitted_at">Sort: submitted date</option>
          <option value="status">Sort: status</option>
          <option value="total_cents">Sort: total amount</option>
        </select>
        <select value={sortDir} onChange={(e) => setSortDir(e.target.value as "asc" | "desc")}>
          <option value="desc">Descending</option>
          <option value="asc">Ascending</option>
        </select>
        <label className="inline-checkbox">
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(e) => {
              setPage(1)
              setIncludeArchived(e.target.checked)
            }}
          />
          Show archived
        </label>
        {user?.role === "approver" && (
          <label className="inline-checkbox">
            <input
              type="checkbox"
              checked={assignedToMe}
              onChange={(e) => {
                setPage(1)
                setAssignedToMe(e.target.checked)
              }}
            />
            Assigned to me
          </label>
        )}
      </div>

      {error && <p className="form-error">{error}</p>}
      {bulkError && <p className="form-error">{bulkError}</p>}
      {!error && data === null && <p>Loading...</p>}
      {data !== null && data.items.length === 0 && <p>No reports found.</p>}

      {user?.role === "approver" && selectedIds.length > 0 && (
        <div className="action-bar">
          <span>{selectedIds.length} selected</span>
          <button disabled={bulkBusy} onClick={() => handleBulk("approved")}>
            Bulk approve
          </button>
          <button disabled={bulkBusy} onClick={() => handleBulk("rejected")}>
            Bulk reject
          </button>
        </div>
      )}

      {bulkResults && (
        <ul className="bulk-results">
          {bulkResults.map((r) => (
            <li key={r.report_id} className={r.ok ? "bulk-ok" : "bulk-fail"}>
              Report #{r.report_id}: {r.ok ? "success" : r.self_owned ? "rejected - you own this report" : `failed - ${r.reason}`}
            </li>
          ))}
        </ul>
      )}

      {data !== null && data.items.length > 0 && (
        <>
          <table className="data-table">
            <thead>
              <tr>
                {user?.role === "approver" && <th />}
                <th>Title</th>
                <th>Owner</th>
                <th>Status</th>
                <th>Total</th>
                <th>Dates</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((r) => (
                <tr key={r.id}>
                  {user?.role === "approver" && (
                    <td>
                      {selectableIds.includes(r.id) && (
                        <input
                          type="checkbox"
                          checked={selectedIds.includes(r.id)}
                          onChange={(e) =>
                            setSelectedIds((prev) =>
                              e.target.checked ? [...prev, r.id] : prev.filter((id) => id !== r.id),
                            )
                          }
                        />
                      )}
                    </td>
                  )}
                  <td>
                    <Link to={`/reports/${r.id}`}>{r.title}</Link>
                    {r.archived_at && <span className="badge">archived</span>}
                  </td>
                  <td>{r.owner.name}</td>
                  <td>
                    <span className={`status-badge status-${r.status}`}>{r.status}</span>
                  </td>
                  <td>{formatCents(r.total_cents)}</td>
                  <td>
                    {r.start_date} - {r.end_date}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="pagination">
            <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              Previous
            </button>
            <span>
              Page {page} of {totalPages} ({data.total} total)
            </span>
            <button disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
              Next
            </button>
          </div>
        </>
      )}
    </Layout>
  )
}
