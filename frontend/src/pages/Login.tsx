import { useState } from "react"
import type { FormEvent } from "react"
import { useNavigate } from "react-router-dom"
import { useAuth } from "../context/AuthContext"
import { ApiError } from "../api/client"

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    // The button's `disabled` only blocks clicks - pressing Enter while a submit is
    // already in flight still fires this handler, so guard it explicitly here.
    if (submitting) return
    setError(null)
    setSubmitting(true)
    try {
      await login(email, password)
      navigate("/dashboard")
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="login-page">
      <form onSubmit={handleSubmit} className="login-form">
        <div>
          <h1>Expense Reimbursement</h1>
          <p className="login-subtitle">Sign in to submit, review, or approve reports.</p>
        </div>
        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoFocus
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {error && <p className="form-error">{error}</p>}
        <button type="submit" className="btn-primary btn-block" disabled={submitting}>
          {submitting ? "Signing in..." : "Sign in"}
        </button>
      </form>
    </div>
  )
}
