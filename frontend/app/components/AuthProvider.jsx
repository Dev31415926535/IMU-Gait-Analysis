"use client"
import { createContext, useContext, useState, useEffect } from "react"
import { users } from "@/lib/utlis"

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const raw = localStorage.getItem("ph_auth")
    if (raw) setUser(JSON.parse(raw))
    setLoading(false)
  }, [])

  function login({ username, password }) {
    const match = users.find(u => u.username === username && u.password === password)
    if (!match) throw new Error("Invalid username or password")

    const loggedIn = { username: match.username, role: match.role, patientId: match.patientId }
    localStorage.setItem("ph_auth", JSON.stringify(loggedIn))
    setUser(loggedIn)
    return loggedIn
  }

  function logout() {
    localStorage.removeItem("ph_auth")
    setUser(null)
  }

  if (loading) return <div>Loading...</div>

  return (
    <AuthContext.Provider value={{ user, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
