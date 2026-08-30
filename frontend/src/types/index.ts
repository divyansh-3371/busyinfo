export type Role = "employee" | "approver"

export interface User {
  id: number
  email: string
  name: string
  role: Role
}
