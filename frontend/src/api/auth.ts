import { apiFetch } from "./client"
import type { User } from "../types"

interface TokenResponse {
  access_token: string
  token_type: string
  user: User
}

export function login(email: string, password: string): Promise<TokenResponse> {
  return apiFetch<TokenResponse>("/auth/login", { method: "POST", body: { email, password } })
}

export function fetchCurrentUser(): Promise<User> {
  return apiFetch<User>("/auth/me")
}
