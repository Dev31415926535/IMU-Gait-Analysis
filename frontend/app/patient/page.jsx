'use client'
import { useEffect, useState, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/app/components/AuthProvider'
import Sidebar from '@/app/components/Sidebar'
import { LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export default function PatientPage() {
  const { user } = useAuth()
  const router = useRouter()

  const [logs, setLogs] = useState('')
  const [patient, setPatient] = useState(null)
  const [recordings, setRecordings] = useState([])
  const [loading, setLoading] = useState(true)
  const [analyzing, setAnalyzing] = useState(false)
  const [error, setError] = useState(null)
  const [selectedData, setSelectedData] = useState(null)
  const [showModal, setShowModal] = useState(false)
  const abortRef = useRef(null)

  useEffect(() => {
    if (user === null) {
      router.replace('/login')
      return
    }
    if (user && user.role !== 'patient') {
      router.replace('/admin')
      return
    }
    if (!user) return

    const currentPatient = {
      id: user.patientId,
      name: user.username,
      status: user.role || 'in-treatment',
      age: user.age ?? '—',
    }
    setPatient(currentPatient)

    const controller = new AbortController()
    abortRef.current = controller

    const fetchRecordings = async () => {
      try {
        setLoading(true)
        setError(null)
        const res = await fetch(
          `${API_BASE}/recordings?patient_id=${encodeURIComponent(currentPatient.id)}&patient_name=${encodeURIComponent(currentPatient.name)}`,
          { signal: controller.signal }
        )

        if (!res.ok) throw new Error(`Failed to fetch recordings (${res.status})`)
        const data = await res.json()
        setRecordings(Array.isArray(data) ? data : [])
      } catch (err) {
        if (err.name !== 'AbortError') {
          console.error(err)
          setError('Failed to load recordings.')
        }
      } finally {
        setLoading(false)
      }
    }

    fetchRecordings()
    return () => controller.abort()
  }, [user, router])

  async function handleGenerateRecording() {
    if (!patient) return
    try {
      setAnalyzing(true)
      setLogs('')

      const response = await fetch(`${API_BASE}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ patient_id: patient.id, name: patient.name }),
      })

      if (!response.ok) throw new Error(`Server error ${response.status}`)
      if (!response.body) throw new Error('No stream body received')

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let logText = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        logText += decoder.decode(value, { stream: true })
        setLogs(logText)
      }

      const recRes = await fetch(`${API_BASE}/recordings?patient_id=${encodeURIComponent(patient.id)}`)
      if (recRes.ok) {
        const updatedRecs = await recRes.json()
        setRecordings(Array.isArray(updatedRecs) ? updatedRecs : [])
      }
    } catch (err) {
      console.error('Failed to generate recording:', err)
      alert('Error generating recording. See console for details.')
    } finally {
      setAnalyzing(false)
    }
  }

  async function handleViewData(recId) {
    try {
      const res = await fetch(`${API_BASE}/recordings/${recId}`)
      if (!res.ok) throw new Error(`Failed to fetch recording ${recId}`)
      const data = await res.json()
      setSelectedData(data)
      setShowModal(true)
    } catch (err) {
      console.error(err)
      alert('Failed to load recording data.')
    }
  }

  function closeModal() {
    setShowModal(false)
    setSelectedData(null)
  }

  if (loading) return <div className="p-6">Loading patient data...</div>
  if (error) return <div className="p-6 text-red-600">{error}</div>
  if (!patient) return <div className="p-6 text-red-600">No matching patient found or not authorized.</div>

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
            {/* <button
              onClick={handleGenerateRecording}
              disabled={analyzing}
              className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded text-sm"
            >
              {analyzing ? 'Generating...' : 'Generate Recording'}
            </button> */}
          </div>

          {recordings.length > 0 ? (
            <div className="space-y-2">
              {recordings.map((rec) => (
                <div
                  key={rec.id}
                  className="flex items-center justify-between bg-gray-50 p-2 rounded-md"
                >
                  <span className="text-sm text-gray-700">{rec.label}</span>
                  <button
                    onClick={() => handleViewData(rec.id)}
                    className="text-xs bg-indigo-600 hover:bg-indigo-700 text-white px-2 py-1 rounded"
                  >
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

          {logs && (
            <pre className="mt-4 max-h-64 overflow-auto text-xs bg-gray-100 p-3 rounded">{logs}</pre>
          )}
        </div>
      </div>

      {/* Modal Visualization */}
      {showModal && selectedData && (
        <div className="fixed inset-0 bg-black bg-opacity-40 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl w-11/12 md:w-3/4 lg:w-1/2 p-6 relative">
            <button
              onClick={closeModal}
              className="absolute top-2 right-3 text-gray-500 hover:text-black"
            >
              ✕
            </button>
            <h3 className="text-lg font-semibold mb-4">{selectedData.label}</h3>
            <div className="w-full h-64">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={selectedData.data}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="time" label={{ value: 'Time (s)', position: 'insideBottomRight', offset: 0 }} />
                  <YAxis label={{ value: 'Angle (°)', angle: -90, position: 'insideLeft' }} />
                  <Tooltip />
                  <Line type="monotone" dataKey="angle" stroke="#3b82f6" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}
    </Sidebar>
  )
}