import { Navigate, Route, Routes } from "react-router-dom"
import "./App.css"
import { AuthProvider } from "./context/AuthContext"
import RequireAuth from "./components/RequireAuth"
import Login from "./pages/Login"
import Dashboard from "./pages/Dashboard"
import ReportsList from "./pages/ReportsList"
import ReportDetail from "./pages/ReportDetail"
import NewReport from "./pages/NewReport"

function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/dashboard"
          element={
            <RequireAuth>
              <Dashboard />
            </RequireAuth>
          }
        />
        <Route
          path="/reports"
          element={
            <RequireAuth>
              <ReportsList />
            </RequireAuth>
          }
        />
        <Route
          path="/reports/new"
          element={
            <RequireAuth>
              <NewReport />
            </RequireAuth>
          }
        />
        <Route
          path="/reports/:id"
          element={
            <RequireAuth>
              <ReportDetail />
            </RequireAuth>
          }
        />
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </AuthProvider>
  )
}

export default App
