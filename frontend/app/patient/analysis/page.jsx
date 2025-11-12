'use client'
import { useState, useRef, useEffect } from 'react'
import { useAuth } from '@/app/components/AuthProvider'
import { useRouter } from 'next/navigation'
import Sidebar from '@/app/components/Sidebar'
import { LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export default function GeneratePage() {
  const { user } = useAuth()
  const router = useRouter()
  const [logs, setLogs] = useState('')
  const [finalData, setFinalData] = useState([])
  const [analyzing, setAnalyzing] = useState(false)
  const [done, setDone] = useState(false)
  const logRef = useRef(null)

  if (!user) return <div className="p-6">Loading user...</div>
  const patient = { id: user.patientId, name: user.username }

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [logs])

  async function handleGenerateRecording() {
    try {
      setAnalyzing(true)
      setLogs('')
      setFinalData([])
      setDone(false)

      const res = await fetch(`${API_BASE}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ patient_id: patient.id, name: patient.name }),
      })

      if (!res.ok) throw new Error(`Server error ${res.status}`)
      if (!res.body) throw new Error('No stream body')

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let newFilename = null

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const chunk = decoder.decode(value, { stream: true })
        buffer += chunk

        const lines = buffer.split('\n')
        buffer = lines.pop()
        for (const line of lines) {
          if (line.includes('📁 Saved new recording for')) {
            const match = line.match(/📁 Saved new recording for .*: (.*_angles\.csv)/)
            if (match && match[1]) {
              newFilename = match[1].replace('.csv', '').trim()
              console.log('📂 Detected saved file:', newFilename)
            }
          }
          setLogs(prev => prev + line + '\n')
        }
      }

      if (newFilename) {
        await fetchAndPlotJSON(newFilename)
      } else {
        console.warn('⚠️ No saved filename detected in logs.')
      }

      setDone(true)
      setLogs(prev => prev + '\n✅ Analysis completed and data saved.\n')
    } catch (err) {
      console.error('Error generating recording:', err)
      alert('Error generating recording. See console for details.')
    } finally {
      setAnalyzing(false)
    }
  }

  async function fetchAndPlotJSON(recordingId) {
    try {
      const res = await fetch(`${API_BASE}/recordings/${recordingId}`)
      if (!res.ok) throw new Error('Failed to fetch recording data')
      const json = await res.json()
      if (json?.data?.length) {
        setFinalData(json.data)
      } else {
        console.warn('⚠️ No data in fetched JSON:', json)
      }
    } catch (err) {
      console.error('Error loading saved recording:', err)
    }
  }

  return (
    <Sidebar>
      <div className="p-6 space-y-6">
        <h2 className="text-2xl font-semibold">Generate New Recording</h2>
        <p className="text-gray-600">
          This will capture IMU data from your ESP32, analyze it, and plot the recorded results.
        </p>

        <button
          onClick={handleGenerateRecording}
          disabled={analyzing}
          className={`px-4 py-2 rounded text-white font-medium ${
            analyzing ? 'bg-gray-400' : 'bg-blue-600 hover:bg-blue-700'
          }`}
        >
          {analyzing ? 'Analyzing...' : 'Start Analysis'}
        </button>

        {/* ✅ Single Chart for Final Saved Recording */}
        {finalData.length > 0 && (
          <div className="bg-white p-4 rounded-lg shadow-md">
            <h3 className="text-lg font-semibold mb-3">Angle Metrics vs Time</h3>
            <div className="w-full h-72">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={finalData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="time" label={{ value: 'Time (s)', position: 'insideBottomRight' }} />
                  <YAxis label={{ value: 'Angle Metrics (°)', angle: -90, position: 'insideLeft' }} />
                  <Tooltip />
                  <Line
                    type="monotone"
                    dataKey="angle_metrics"
                    stroke="#3b82f6"
                    strokeWidth={2}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Logs */}
        <div
          ref={logRef}
          className="bg-black text-green-400 font-mono p-4 rounded-md max-h-[60vh] overflow-auto whitespace-pre-wrap"
        >
          {logs || 'Logs will appear here...'}
        </div>

        {done && (
          <button
            onClick={() => router.push('/patient')}
            className="mt-4 text-blue-600 hover:underline"
          >
            ← Back to My Recordings
          </button>
        )}
      </div>
    </Sidebar>
  )
}
