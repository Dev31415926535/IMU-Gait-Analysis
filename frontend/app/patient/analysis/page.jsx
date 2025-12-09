// 'use client'
// import { useState, useRef, useEffect } from 'react'
// import { useAuth } from '@/app/components/AuthProvider'
// import { useRouter } from 'next/navigation'
// import Sidebar from '@/app/components/Sidebar'
// import { LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

// const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// export default function GeneratePage() {
//   const { user } = useAuth()
//   const router = useRouter()
//   useEffect(() => {
//     if (user === null) {
//       router.replace('/login')
//     }
//   }, [user, router])
//   const [report, setReport] = useState(null)
//   const [logs, setLogs] = useState('')
//   const [finalData, setFinalData] = useState([])
//   const [analyzing, setAnalyzing] = useState(false)
//   const [done, setDone] = useState(false)
//   const logRef = useRef(null)

//   const patient = user ? { id: user.patientId, name: user.username } : null

//   useEffect(() => {
//     if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
//   }, [logs])

//   async function handleGenerateRecording() {
//     try {
//       setAnalyzing(true)
//       setLogs('')
//       setFinalData([])
//       setDone(false)

//       const res = await fetch(`${API_BASE}/analyze`, {
//         method: 'POST',
//         headers: { 'Content-Type': 'application/json' },
//         body: JSON.stringify({ patient_id: patient.id, name: patient.name }),
//       })

//       if (!res.ok) throw new Error(`Server error ${res.status}`)
//       if (!res.body) throw new Error('No stream body')

//       const reader = res.body.getReader()
//       const decoder = new TextDecoder()
//       let buffer = ''
//       let newFilename = null

//       while (true) {
//         const { done, value } = await reader.read()
//         if (done) break
//         const chunk = decoder.decode(value, { stream: true })
//         buffer += chunk

//         const lines = buffer.split('\n')
//         buffer = lines.pop()
//         for (const line of lines) {
//           if (line.includes('📁 Saved new recording for')) {
//             const match = line.match(/Saved new recording for .*: (.*_angles\.csv)/)
//             if (match && match[1]) {
//               newFilename = match[1].replace('.csv', '').trim()
//               console.log('📂 Detected saved file:', newFilename)
//             }
//           }
//           setLogs(prev => prev + line + '\n')
//         }
//       }

//       if (newFilename) {
//         await fetchAndPlotJSON(newFilename)
//       } else {
//         console.warn('⚠️ No saved filename detected in logs.')
//       }

//       setDone(true)
//       setLogs(prev => prev + '\n Analysis completed and data saved.\n')
//     } catch (err) {
//       console.error('Error generating recording:', err)
//       alert('Error generating recording. See console for details.')
//     } finally {
//       setAnalyzing(false)
//     }
//   }

//   async function fetchAndPlotJSON(recordingId) {
//     try {
//       const res = await fetch(
//         `${API_BASE}/recordings/${recordingId}?patient_name=${patient.name}`
//       );

//       if (!res.ok) throw new Error("Failed to fetch recording data");

//       const json = await res.json();

//       if (!json.angles) {
//         console.warn(" No angles in JSON:", json);
//         return;
//       }

//       // Convert angles JSON -> chart friendly array
//       const left = json.angles.left_leg?.angles || [];
//       const right = json.angles.right_leg?.angles || [];
//       const maxLen = Math.max(left.length, right.length);

//       const combined = [];
//       for (let i = 0; i < maxLen; i++) {
//         combined.push({
//           time: i,
//           left: left[i] ?? null,
//           right: right[i] ?? null,
//         });
//       }

//       setFinalData(combined);
//       setReport(json.report || null);

//     } catch (err) {
//       console.error("Error loading saved recording:", err);
//     }
//   }


//   return (
//     <Sidebar>
//       {!user ? (
//         <div className="p-6">Loading user...</div>
//       ) : (
//       <div className="p-6 space-y-6">
//         <h2 className="text-2xl font-semibold">Generate New Recording</h2>
//         <p className="text-gray-600">
//           This will capture IMU data from your ESP32, analyze it, and plot the recorded results.
//         </p>

//         <button
//           onClick={handleGenerateRecording}
//           disabled={analyzing}
//           className={`px-4 py-2 rounded text-white font-medium ${
//             analyzing ? 'bg-gray-400' : 'bg-blue-600 hover:bg-blue-700'
//           }`}
//         >
//           {analyzing ? 'Analyzing...' : 'Start Analysis'}
//         </button>

//         {/*  Single Chart for Final Saved Recording */}
//         {finalData.length > 0 && (
//           <div className="bg-white p-4 rounded-lg shadow-md">
//             <h3 className="text-lg font-semibold mb-3">Angle Metrics vs Time</h3>
//             <div className="w-full h-72">
//               <ResponsiveContainer width="100%" height="100%">
//                 <LineChart data={finalData}>
//                   <CartesianGrid strokeDasharray="3 3" />
//                   <XAxis dataKey="time" label={{ value: 'Time (s)', position: 'insideBottomRight' }} />
//                   <YAxis label={{ value: 'Angle Metrics (°)', angle: -90, position: 'insideLeft' }} />
//                   <Tooltip />
//                   <Line
//                     type="monotone"
//                     dataKey="angle_metrics"
//                     stroke="#3b82f6"
//                     strokeWidth={2}
//                     dot={false}
//                   />
//                 </LineChart>
//               </ResponsiveContainer>
//             </div>
//           </div>
//         )}
// {/* ----------------------------- */}
// {/* Gait Report Section           */}
// {/* ----------------------------- */}
// {report && (
//   <div className="bg-white p-4 rounded-lg shadow-md">
//     <h3 className="text-lg font-semibold mb-3">Gait Report</h3>

//     <div className="space-y-2 text-gray-700">
//       {Object.entries(report).map(([key, value]) => (
//         <div key={key} className="border-b py-1">
//           <span className="font-semibold capitalize">
//             {key.replace(/_/g, ' ')}:
//           </span>{" "}
//           {typeof value === "number" ? value.toFixed(2) : String(value)}
//         </div>
//       ))}
//     </div>
//   </div>
// )}

//         {/* Logs */}
//         <div
//           ref={logRef}
//           className="bg-black text-green-400 font-mono p-4 rounded-md max-h-[60vh] overflow-auto whitespace-pre-wrap"
//         >
//           {logs || 'Logs will appear here...'}
//         </div>

//         {done && (
//           <button
//             onClick={() => router.push('/patient')}
//             className="mt-4 text-blue-600 hover:underline"
//           >
//             ← Back to My Recordings
//           </button>
//         )}
//       </div>
//       )}
//     </Sidebar>
//   )
// }
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

  const [report, setReport] = useState(null)
  const [logs, setLogs] = useState('')
  const [finalData, setFinalData] = useState([])
  const [analyzing, setAnalyzing] = useState(false)
  const [done, setDone] = useState(false)
  const logRef = useRef(null)

  const patient = user ? { id: user.patientId, name: user.username } : null

  // redirect if not logged in
  useEffect(() => {
    if (user === null) {
      router.replace('/login')
    }
  }, [user, router])

  // auto-scroll logs
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [logs])

  async function handleGenerateRecording() {
    if (!patient) return

    try {
      setAnalyzing(true)
      setLogs('')
      setFinalData([])
      setReport(null)
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

      // read streaming logs
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const chunk = decoder.decode(value, { stream: true })
        buffer += chunk

        const lines = buffer.split('\n')
        buffer = lines.pop() // keep partial line
        for (const line of lines) {
          if (line.trim().length === 0) continue
          setLogs(prev => prev + line + '\n')
        }
      }

      // ✅ After analysis finishes, fetch latest recording from /patients
      await fetchLatestRecording()

      setDone(true)
      setLogs(prev => prev + '\nAnalysis completed and data saved.\n')
    } catch (err) {
      console.error('Error generating recording:', err)
      alert('Error generating recording. See console for details.')
    } finally {
      setAnalyzing(false)
    }
  }

  // Get latest recording ID for this patient and then load its metrics+report
  async function fetchLatestRecording() {
    if (!patient) return
    try {
      const res = await fetch(`${API_BASE}/patients/${patient.id}`)
      if (!res.ok) throw new Error('Failed to fetch patient recordings')

      const patientData = await res.json()
      const recs = patientData.recordings || []

      if (!recs.length) {
        console.warn('No recordings found for patient')
        return
      }

      const latest = recs[0] // newest first (backend sorts)
      if (!latest.id) {
        console.warn('Latest recording has no id:', latest)
        return
      }

      await fetchAndPlotJSON(latest.id)
    } catch (err) {
      console.error('Error fetching latest recording:', err)
    }
  }

  async function fetchAndPlotJSON(recordingId) {
    if (!patient) return

    try {
      const res = await fetch(
        `${API_BASE}/recordings/${recordingId}?patient_name=${patient.name}`
      )
      if (!res.ok) throw new Error('Failed to fetch recording data')

      const json = await res.json()
      console.log('Recording JSON (debug):', json)

      // Be flexible: different routes/pages may shape it differently
      const payload =
        json.data ||           // old format: { id, label, data: {...} }
        json.angles ||         // newer format: { id, angles: {...}, report: {...} }
        json.metrics ||        // just in case
        json

      // Try multiple possible angle locations
      const left =
        payload.left_leg?.angles ||
        payload.left_knee_angles ||
        payload.left_leg_angles ||
        []

      const right =
        payload.right_leg?.angles ||
        payload.right_knee_angles ||
        payload.right_leg_angles ||
        []

      if (!left.length && !right.length) {
        console.warn('No angle arrays found in payload:', payload)
      }

      const maxLen = Math.max(left.length, right.length)
      const combined = []
      for (let i = 0; i < maxLen; i++) {
        combined.push({
          time: i,
          left: left[i] ?? null,
          right: right[i] ?? null,
        })
      }

      setFinalData(combined)

      // Gait report may be in json.report or inside payload
      const reportObj =
        json.report ||
        payload.report ||
        payload.gait_report ||
        null

      setReport(reportObj)
    } catch (err) {
      console.error('Error loading saved recording:', err)
    }
  }

  return (
    <Sidebar>
      {!user ? (
        <div className="p-6">Loading user...</div>
      ) : (
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

          {/*  Final Chart for Latest Saved Recording */}
          {finalData.length > 0 && (
            <div className="bg-white p-4 rounded-lg shadow-md">
              <h3 className="text-lg font-semibold mb-3">Knee Angles vs Time</h3>
              <div className="w-full h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={finalData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis
                      dataKey="time"
                      label={{ value: 'Frame / Time Index', position: 'insideBottomRight' }}
                    />
                    <YAxis
                      label={{
                        value: 'Angle (°)',
                        angle: -90,
                        position: 'insideLeft',
                      }}
                    />
                    <Tooltip />
                    <Line
                      type="monotone"
                      dataKey="left"
                      name="Left Knee"
                      stroke="#3b82f6"
                      strokeWidth={2}
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="right"
                      name="Right Knee"
                      stroke="#ef4444"
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Gait Report Section */}
          {report && (
            <div className="bg-white p-4 rounded-lg shadow-md">
              <h3 className="text-lg font-semibold mb-3">Gait Report</h3>
              <div className="space-y-2 text-gray-700">
                {Object.entries(report).map(([key, value]) => (
                  <div key={key} className="border-b py-1">
                    <span className="font-semibold capitalize">
                      {key.replace(/_/g, ' ')}:
                    </span>{' '}
                    {typeof value === 'number' ? value.toFixed(2) : String(value)}
                  </div>
                ))}
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
      )}
    </Sidebar>
  )
}
