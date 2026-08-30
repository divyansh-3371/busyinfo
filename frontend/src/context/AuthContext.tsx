import { createContext, useContext, useEffect, useState } from "react"
import type { ReactNode } from "react"
import { fetchCurrentUser, login as loginRequest } from "../api/auth"
import { clearToken, getToken, onUnauthorized, setToken } from "../api/authToken"
import type { User } from "../types"

interface AuthContextValue {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  // Starts true whenever a token is already stored, so a page refresh doesn't flash
  // the login screen before we've had a chance to validate the token.
  const [loading, setLoading] = useState<boolean>(!!getToken())

  useEffect(() => {
    onUnauthorized(() => setUser(null))
  }, [])

  useEffect(() => {
    if (!getToken()) {
      setLoading(false)
      return
    }
    fetchCurrentUser()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [])

  async function login(email: string, password: string) {
    const response = await loginRequest(email, password)
    setToken(response.access_token)
    setUser(response.user)
  }

  function logout() {
    clearToken()
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider")
  return ctx
}
