import type { ReactNode } from "react"
import { Link } from "react-router-dom"
import { useAuth } from "../context/AuthContext"

export default function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth()

  return (
    <div>
      <header className="app-header">
        <nav className="app-nav">
          <Link to="/dashboard">Dashboard</Link>
          <Link to="/reports">Reports</Link>
          <Link to="/reports/new">New report</Link>
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
