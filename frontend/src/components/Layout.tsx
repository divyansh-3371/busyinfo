import type { ReactNode } from "react"
import { useEffect, useState } from "react"
import { NavLink } from "react-router-dom"
import { useAuth } from "../context/AuthContext"
import { listAlerts } from "../api/alerts"
import { getNeedsAttentionCount } from "../api/reports"

export default function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth()
  const [alertCount, setAlertCount] = useState(0)
  const [needsAttentionCount, setNeedsAttentionCount] = useState(0)

  useEffect(() => {
    if (user?.role === "approver") {
      listAlerts()
        .then((alerts) => setAlertCount(alerts.length))
        .catch(() => setAlertCount(0))
    }
  }, [user])

  useEffect(() => {
    // Not role-gated like the alert count above - anyone who owns a report can
    // have it rejected, approvers included, since they submit their own
    // expenses too. This app sends no email/push notifications at all, so this
    // badge is the only proactive signal a rejection happened.
    if (user) {
      getNeedsAttentionCount()
        .then(({ count }) => setNeedsAttentionCount(count))
        .catch(() => setNeedsAttentionCount(0))
    }
  }, [user])

  const initial = user?.name?.trim()?.[0]?.toUpperCase() ?? "?"

  return (
    <div className="app-shell">
      <header className="app-header">
        <span className="app-brand">
          <span className="app-brand-mark">🧾</span>
          Expenses
        </span>
        <nav className="app-nav">
          <NavLink to="/dashboard">Dashboard</NavLink>
          <NavLink to="/reports" end>
            Reports
            {needsAttentionCount > 0 && <span className="nav-badge">{needsAttentionCount}</span>}
          </NavLink>
          <NavLink to="/reports/new">New report</NavLink>
          {user?.role === "approver" && (
            <NavLink to="/alerts">
              Alerts{alertCount > 0 && <span className="nav-badge">{alertCount}</span>}
            </NavLink>
          )}
        </nav>
        <span className="app-user">
          <span className="app-user-avatar">{initial}</span>
          <span className="app-user-meta">
            <span className="app-user-name">{user?.name}</span>
            <span className="app-user-role">{user?.role}</span>
          </span>
          <button className="btn-ghost btn-sm" onClick={logout}>
            Log out
          </button>
        </span>
      </header>
      <main className="app-main">{children}</main>
    </div>
  )
}
