'use client'
import { useState, useEffect, useRef } from 'react'
import { useAuth } from '@/app/components/AuthProvider'
import { useRouter } from 'next/navigation'
import Sidebar from '@/app/components/Sidebar'
import { LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export default function GeneratePage() {
  const { user } = useAuth()
  const router = useRouter()
  const [logs, setLogs] = useState('')
  const [data, setData] = useState([]) // live plot data
  const [analyzing, setAnalyzing] = useState(false)
  const [done, setDone] = useState(false)
  const abortRef = useRef(null)

  if (!user) return <div className="p-6">Loading user...</div>
  const patient = { id: user.patientId, name: user.username }

  async function handleGenerateRecording() {
    try {
      setAnalyzing(true)
      setLogs('')
      setData([])

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

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const chunk = decoder.decode(value, { stream: true })
        buffer += chunk

        // Parse line by line
        const lines = buffer.split('\n')
        buffer = lines.pop() // incomplete last line stays in buffer
        for (const line of lines) {
          if (line.startsWith('STREAM_DATA')) {
            const parts = line.split(' ')[1]?.split(',')
            if (parts && parts.length === 2) {
              const time = parseFloat(parts[0])
              const angle = parseFloat(parts[1])
              if (!isNaN(time) && !isNaN(angle)) {
                setData(prev => [...prev, { time, angle }])
              }
            }
          } else {
            setLogs(prev => prev + line + '\n')
          }
        }
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

  return (
    <Sidebar>
      <div className="p-6 space-y-6">
        <h2 className="text-2xl font-semibold">Generate New Recording</h2>
        <p className="text-gray-600">
          This will capture IMU data from your ESP32 in real time and analyze it.
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

        {/* Live Plot */}
        {data.length > 0 && (
          <div className="bg-white p-4 rounded-lg shadow-md">
            <h3 className="text-lg font-semibold mb-3">Live Angle Data</h3>
            <div className="w-full h-72">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="time" label={{ value: 'Time (s)', position: 'insideBottomRight' }} />
                  <YAxis label={{ value: 'Angle (°)', angle: -90, position: 'insideLeft' }} />
                  <Tooltip />
                  <Line type="monotone" dataKey="angle" stroke="#22c55e" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Live Logs */}
        <div className="bg-black text-green-400 font-mono p-4 rounded-md max-h-[60vh] overflow-auto whitespace-pre-wrap">
          {logs ? logs : 'Logs will appear here...'}
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
