'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/app/components/AuthProvider'
import Sidebar from '@/app/components/Sidebar'

// Dummy patient data (simulate a DB)
const patients = [
  {
    id: '34589592-2c31-4343-ad16-b7801a90b09d',
    name: 'dev',
    age: 19,
    status: 'in-treatment',
  },
  {
    id: '880f5383-a4e3-4a38-a13b-b59c17cfc1d6',
    name: 'John Doe',
    age: 25,
    status: 'pending',
    recordings: [
      { id: 'r1', label: 'Rehab Session 2025-10-23' },
      { id: 'r2', label: 'General Checkup 2025-10-24' },
    ],
  },
  {
    id: '7fd4e870-de98-4715-9f2c-abe7f6bb5adb',
    name: 'Jane Smith',
    age: 32,
    status: 'in-treatment',
  },
]

export default function PatientPage() {
  const { user, logout } = useAuth()
  const router = useRouter()

  const [patient, setPatient] = useState(null)
  const [recordings, setRecordings] = useState([])
  const [loading, setLoading] = useState(true)
  const [analyzing, setAnalyzing] = useState(false)

  // Check authentication
  useEffect(() => {
    if (user === null) {
      // no user logged in → redirect to login
      router.replace('/login')
      return
    }
    if (user.role !== 'patient') {
      // admin trying to access patient page → redirect to admin
      router.replace('/admin')
      return
    }

    // If patient is logged in → load their data
    const p = patients.find(
      (pt) => pt.name.toLowerCase() === user.username.toLowerCase()
    )
    setPatient(p)
    setRecordings(p?.recordings || [])
    setLoading(false)
  }, [user, router])

  async function handleGenerateRecording() {
    if (!patient) return
    try {
      setAnalyzing(true)
      const res = await fetch('/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ patientId: patient.id }),
      })
      const data = await res.json()
      // Append the new recording
      setRecordings((prev) => [...prev, data])
    } catch (err) {
      console.error('Failed to generate recording:', err)
      alert('Error generating recording.')
    } finally {
      setAnalyzing(false)
    }
  }

  if (loading) return <div className="p-6">Loading patient data...</div>
  if (!patient)
    return (
      <div className="p-6 text-red-600">
        No matching patient found or not authorized.
      </div>
    )

  return (
    <Sidebar>
      <div className="p-6 space-y-6">
        <div className="flex justify-between items-center">
          <h2 className="text-2xl font-semibold">Welcome, {patient.name}</h2>
        </div>

        <div className="bg-white p-4 rounded shadow">
          <p>Age: {patient.age}</p>
          <p>Status: {patient.status}</p>
        </div>

        {/* Recordings Section */}
        <div className="bg-white p-4 rounded shadow space-y-4">
          <div className="flex justify-between items-center">
            <h3 className="font-medium text-lg">Your Recordings</h3>
            <button
              onClick={handleGenerateRecording}
              disabled={analyzing}
              className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded text-sm"
            >
              {analyzing ? 'Generating...' : 'Generate Recording'}
            </button>
          </div>

          {recordings.length > 0 ? (
            <div className="space-y-2">
              {recordings.map((rec) => (
                <div
                  key={rec.id}
                  className="flex items-center justify-between bg-gray-50 p-2 rounded-md"
                >
                  <span className="text-sm text-gray-700">{rec.label}</span>
                  <button className="text-xs bg-indigo-600 hover:bg-indigo-700 text-white px-2 py-1 rounded">
                    View Data
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <div className="bg-yellow-50 border border-yellow-200 p-3 rounded text-sm text-gray-700">
              No recordings available. Click “Generate Recording” to analyze your session.
            </div>
          )}
        </div>
      </div>
    </Sidebar>
  )
}
