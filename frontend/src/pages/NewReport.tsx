import { useState } from "react"
import type { FormEvent } from "react"
import { useNavigate } from "react-router-dom"
import Layout from "../components/Layout"
import { createReport } from "../api/reports"
import { ApiError } from "../api/client"

export default function NewReport() {
  const navigate = useNavigate()
  const [title, setTitle] = useState("")
  const [startDate, setStartDate] = useState("")
  const [endDate, setEndDate] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const report = await createReport({ title, start_date: startDate, end_date: endDate })
      navigate(`/reports/${report.id}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create report.")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Layout>
      <h1>New expense report</h1>
      <form onSubmit={handleSubmit} className="stacked-form">
        <label>
          Title
          <input value={title} onChange={(e) => setTitle(e.target.value)} required autoFocus />
        </label>
        <label>
          Start date
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            required
          />
        </label>
        <label>
          End date
          <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} required />
        </label>
        {error && <p className="form-error">{error}</p>}
        <button type="submit" disabled={submitting}>
          {submitting ? "Creating..." : "Create draft"}
        </button>
      </form>
    </Layout>
  )
}
