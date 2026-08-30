// Holds the JWT client-side (Authorization: Bearer, not an httpOnly cookie - see
// docs/decisions.md for why: frontend and backend are on different origins).
// localStorage persists it across a refresh; onUnauthorized lets the API client
// force a logout without importing React context directly (avoids a circular import).

const STORAGE_KEY = "expense_app_token"

let token: string | null = localStorage.getItem(STORAGE_KEY)
let unauthorizedHandler: (() => void) | null = null

export function getToken(): string | null {
  return token
}

export function setToken(next: string): void {
  token = next
  localStorage.setItem(STORAGE_KEY, next)
}

export function clearToken(): void {
  token = null
  localStorage.removeItem(STORAGE_KEY)
}

export function onUnauthorized(handler: () => void): void {
  unauthorizedHandler = handler
}

export function notifyUnauthorized(): void {
  unauthorizedHandler?.()
}
