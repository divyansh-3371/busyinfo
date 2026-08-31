import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import Layout from "../components/Layout"
import { listReports } from "../api/reports"
import { ApiError } from "../api/client"
import type { ReportListItem } from "../types"
import { formatCents } from "../types"

export default function ReportsList() {
  const [reports, setReports] = useState<ReportListItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [includeArchived, setIncludeArchived] = useState(false)

  useEffect(() => {
    setReports(null)
    setError(null)
    listReports(includeArchived)
      .then(setReports)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load reports."))
  }, [includeArchived])

  return (
    <Layout>
      <div className="page-header">
        <h1>Reports</h1>
        <label className="inline-checkbox">
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(e) => setIncludeArchived(e.target.checked)}
          />
          Show archived
        </label>
      </div>

      {error && <p className="form-error">{error}</p>}
      {!error && reports === null && <p>Loading...</p>}
      {reports !== null && reports.length === 0 && <p>No reports found.</p>}

      {reports !== null && reports.length > 0 && (
        <table className="data-table">
          <thead>
            <tr>
              <th>Title</th>
              <th>Owner</th>
              <th>Status</th>
              <th>Total</th>
              <th>Dates</th>
            </tr>
          </thead>
          <tbody>
            {reports.map((r) => (
              <tr key={r.id}>
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
      )}
    </Layout>
  )
}
