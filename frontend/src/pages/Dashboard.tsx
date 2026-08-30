import { useAuth } from "../context/AuthContext"

// Placeholder until the real dashboard (headline numbers, breakdowns, 8-week chart -
// goal 8) is built later in the plan. This exists now just to prove the auth flow
// works end to end.
export default function Dashboard() {
  const { user, logout } = useAuth()

  return (
    <div>
      <header className="app-header">
        <span>
          Signed in as {user?.name} ({user?.role})
        </span>
        <button onClick={logout}>Log out</button>
      </header>
      <p>Dashboard placeholder - built in a later commit.</p>
    </div>
  )
}
