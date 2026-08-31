import type { ReactNode } from "react"
import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { useAuth } from "../context/AuthContext"
import { listAlerts } from "../api/alerts"

export default function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth()
  const [alertCount, setAlertCount] = useState(0)

  useEffect(() => {
    if (user?.role === "approver") {
      listAlerts()
        .then((alerts) => setAlertCount(alerts.length))
        .catch(() => setAlertCount(0))
    }
  }, [user])

  return (
    <div>
      <header className="app-header">
        <nav className="app-nav">
          <Link to="/dashboard">Dashboard</Link>
          <Link to="/reports">Reports</Link>
          <Link to="/reports/new">New report</Link>
          {user?.role === "approver" && (
            <Link to="/alerts">
              Alerts{alertCount > 0 && <span className="nav-badge">{alertCount}</span>}
            </Link>
          )}
        </nav>
        <span className="app-user">
          {user?.name} ({user?.role})
          <button onClick={logout}>Log out</button>
        </span>
      </header>
      <main>{children}</main>
    </div>
  )
}
