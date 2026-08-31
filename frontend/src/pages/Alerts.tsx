import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import Layout from "../components/Layout"
import { dismissAlert, listAlerts } from "../api/alerts"
import { ApiError } from "../api/client"
import type { ReportListItem } from "../types"
import { formatCents } from "../types"

export default function Alerts() {
  const [alerts, setAlerts] = useState<ReportListItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)

  function reload() {
    listAlerts()
      .then(setAlerts)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load alerts."))
  }

  useEffect(reload, [])

  async function handleDismiss(id: number) {
    setBusyId(id)
    try {
      await dismissAlert(id)
      reload()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to dismiss.")
    } finally {
      setBusyId(null)
    }
  }

  return (
    <Layout>
      <h1>Stale approval alerts</h1>
      <p>Reports that have been sitting in Submitted too long without a decision.</p>
      {error && <p className="form-error">{error}</p>}
      {alerts === null && !error && <p>Loading...</p>}
      {alerts !== null && alerts.length === 0 && <p>No stale reports right now.</p>}
      {alerts !== null && alerts.length > 0 && (
        <table className="data-table">
          <thead>
            <tr>
              <th>Title</th>
              <th>Owner</th>
              <th>Total</th>
              <th>Submitted</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {alerts.map((r) => (
              <tr key={r.id}>
                <td>
                  <Link to={`/reports/${r.id}`}>{r.title}</Link>
                </td>
                <td>{r.owner.name}</td>
                <td>{formatCents(r.total_cents)}</td>
                <td>{r.submitted_at ? new Date(r.submitted_at).toLocaleDateString() : "-"}</td>
                <td>
                  <button disabled={busyId === r.id} onClick={() => handleDismiss(r.id)}>
                    Dismiss
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Layout>
  )
}
