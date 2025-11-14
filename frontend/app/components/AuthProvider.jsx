"use client"
import { createContext, useContext, useState, useEffect } from "react"
import { useRouter } from "next/navigation"

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [availableUsers, setAvailableUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const router = useRouter()

  // Load auth + fetch usernames ONCE
  useEffect(() => {
    const raw = localStorage.getItem("ph_auth")
    if (raw) setUser(JSON.parse(raw))

    fetch("http://localhost:8000/users")
      .then(res => res.json())
      .then(data => setAvailableUsers(data))
      .finally(() => setLoading(false))
  }, [])

  function login({ username, password }) {
    const input = username.trim()

    // ----------------------------------------------------
    // 1️⃣ SPECIAL ADMIN LOGIN (username = admin, pass = admin)
    // ----------------------------------------------------
    if (input.toLowerCase() === "admin" && password === "admin") {
      const loggedIn = {
        username: "Admin",
        role: "admin"
      }
      localStorage.setItem("ph_auth", JSON.stringify(loggedIn))
      setUser(loggedIn)
      router.push("/admin")
      return loggedIn
    }

    // ----------------------------------------------------
    // 2️⃣ NORMAL USERS: password must be 123
    // ----------------------------------------------------
    if (password !== "123") {
      throw new Error("Invalid username or password")
    }

    // ----------------------------------------------------
    // 3️⃣ UNIVERSAL NAME NORMALIZATION
    // "Arya Mundra"   → "arya_mundra"
    // "John Doe"      → "john_doe"
    // "Sita Kumari"   → "sita_kumari"
    // ----------------------------------------------------
    const normalizedUsername = input
      .toLowerCase()
      .replace(/\s+/g, "_") // spaces → underscores
      .replace(/[^a-z0-9_]/g, "") // remove invalid characters

    // Match backend list
    const match = availableUsers.find(
      u => u.username.toLowerCase() === normalizedUsername
    )

    if (!match) {
      throw new Error("Invalid username or password")
    }

    // Save pretty/display name EXACTLY as user typed
    const displayName = input

    const loggedIn = {
      username: displayName,       // pretty name
      role: match.role,
      patientId: match.username,   // backend ID
    }

    localStorage.setItem("ph_auth", JSON.stringify(loggedIn))
    setUser(loggedIn)

    // Redirect based on role
    if (match.role === "admin") router.push("/admin")
    else router.push("/patient")

    return loggedIn
  }

  function logout() {
    localStorage.removeItem("ph_auth")
    setUser(null)
  }

  if (loading) return <div>Loading...</div>

  return (
    <AuthContext.Provider value={{ user, login, logout, availableUsers }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}