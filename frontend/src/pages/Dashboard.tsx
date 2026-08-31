import { useEffect, useState } from "react"
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import Layout from "../components/Layout"
import { getDashboard } from "../api/dashboard"
import type { DashboardData } from "../api/dashboard"
import { ApiError } from "../api/client"
import { formatCents } from "../types"

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getDashboard()
      .then(setData)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load dashboard."))
  }, [])

  return (
    <Layout>
      <h1>Dashboard</h1>
      {error && <p className="form-error">{error}</p>}
      {!error && !data && <p>Loading...</p>}
      {data && (
        <>
          <div className="stat-grid">
            <div className="stat-tile">
              <span className="stat-value">{data.awaiting_approval_count}</span>
              <span className="stat-label">Awaiting approval</span>
            </div>
            <div className="stat-tile">
              <span className="stat-value">{formatCents(data.total_due_cents)}</span>
              <span className="stat-label">Total reimbursements due</span>
            </div>
            <div className="stat-tile">
              <span className="stat-value">{data.approved_this_week_count}</span>
              <span className="stat-label">Approved this week</span>
            </div>
            <div className="stat-tile">
              <span className="stat-value">{data.paid_this_week_count}</span>
              <span className="stat-label">Paid this week</span>
            </div>
          </div>

          <div className="breakdown-row">
            <section>
              <h2>By status</h2>
              <ul className="breakdown-list">
                {Object.entries(data.status_breakdown).map(([status, count]) => (
                  <li key={status}>
                    <span className={`status-badge status-${status}`}>{status}</span> {count}
                  </li>
                ))}
              </ul>
            </section>
            <section>
              <h2>By category</h2>
              <ul className="breakdown-list">
                {Object.entries(data.category_breakdown).map(([category, cents]) => (
                  <li key={category}>
                    {category}: {formatCents(cents)}
                  </li>
                ))}
              </ul>
            </section>
          </div>

          <section>
            <h2>Paid per week (last 8 weeks)</h2>
            <div style={{ width: "100%", height: 260 }}>
              <ResponsiveContainer>
                <BarChart data={data.paid_per_week.map((w) => ({ ...w, dollars: w.total_cents / 100 }))}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="week_start" />
                  <YAxis />
                  <Tooltip formatter={(value) => `$${Number(value).toFixed(2)}`} />
                  <Bar dataKey="dollars" fill="#4a7dbf" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </section>
        </>
      )}
    </Layout>
  )
}
