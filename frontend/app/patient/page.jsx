// 'use client'
// import { useEffect, useState, useRef } from 'react'
// import { useRouter } from 'next/navigation'
// import { useAuth } from '@/app/components/AuthProvider'
// import Sidebar from '@/app/components/Sidebar'
// import { LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

// const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// export default function PatientPage() {
//   const { user } = useAuth()
//   const router = useRouter()

//   const [logs, setLogs] = useState('')
//   const [patient, setPatient] = useState(null)
//   const [recordings, setRecordings] = useState([])
//   const [loading, setLoading] = useState(true)
//   const [analyzing, setAnalyzing] = useState(false)
//   const [error, setError] = useState(null)
//   const [selectedData, setSelectedData] = useState(null)
//   const [showModal, setShowModal] = useState(false)
//   const abortRef = useRef(null)

//   useEffect(() => {
//     if (user === null) {
//       router.replace('/login')
//       return
//     }
//     if (user && user.role !== 'patient') {
//       router.replace('/admin')
//       return
//     }
//     if (!user) return

//     const currentPatient = {
//       id: user.patientId,
//       name: user.username,
//       status: user.role || 'in-treatment',
//       age: user.age ?? '—',
//     }
//     setPatient(currentPatient)

//     const controller = new AbortController()
//     abortRef.current = controller

//     const fetchRecordings = async () => {
//       try {
//         setLoading(true)
//         setError(null)
//         const res = await fetch(
//           `${API_BASE}/recordings?patient_id=${encodeURIComponent(currentPatient.id)}&patient_name=${encodeURIComponent(currentPatient.name)}`,
//           { signal: controller.signal }
//         )

//         if (!res.ok) throw new Error(`Failed to fetch recordings (${res.status})`)
//         const data = await res.json()
//         setRecordings(Array.isArray(data) ? data : [])
//       } catch (err) {
//         if (err.name !== 'AbortError') {
//           console.error(err)
//           setError('Failed to load recordings.')
//         }
//       } finally {
//         setLoading(false)
//       }
//     }

//     fetchRecordings()
//     return () => controller.abort()
//   }, [user, router])

//   async function handleGenerateRecording() {
//     if (!patient) return
//     try {
//       setAnalyzing(true)
//       setLogs('')

//       const response = await fetch(`${API_BASE}/analyze`, {
//         method: 'POST',
//         headers: { 'Content-Type': 'application/json' },
//         body: JSON.stringify({ patient_id: patient.id, name: patient.name }),
//       })

//       if (!response.ok) throw new Error(`Server error ${response.status}`)
//       if (!response.body) throw new Error('No stream body received')

//       const reader = response.body.getReader()
//       const decoder = new TextDecoder()
//       let logText = ''

//       while (true) {
//         const { done, value } = await reader.read()
//         if (done) break
//         logText += decoder.decode(value, { stream: true })
//         setLogs(logText)
//       }

//       const recRes = await fetch(`${API_BASE}/recordings?patient_id=${encodeURIComponent(patient.id)}`)
//       if (recRes.ok) {
//         const updatedRecs = await recRes.json()
//         setRecordings(Array.isArray(updatedRecs) ? updatedRecs : [])
//       }
//     } catch (err) {
//       console.error('Failed to generate recording:', err)
//       alert('Error generating recording. See console for details.')
//     } finally {
//       setAnalyzing(false)
//     }
//   }

//   async function handleViewData(recId) {
//     try {
//       const res = await fetch(
//         `${API_BASE}/recordings/${recId}?patient_name=${encodeURIComponent(patient.name)}`
//       )
//       if (!res.ok) throw new Error(`Failed to fetch recording ${recId}`)
//       const data = await res.json()
// console.log("📌 Loaded REPORT DATA:", data.report);

//       setSelectedData(data)
//       setShowModal(true)
//     } catch (err) {
//       console.error(err)
//       alert('Failed to load recording data.')
//     }
//   }

//   function closeModal() {
//     setShowModal(false)
//     setSelectedData(null)
//   }

//   if (loading) return <div className="p-6">Loading patient data...</div>
//   if (error) return <div className="p-6 text-red-600">{error}</div>
//   if (!patient) return <div className="p-6 text-red-600">No matching patient found or not authorized.</div>

//   return (
//     <Sidebar>
//       <div className="p-6 space-y-6">
//         <div className="flex justify-between items-center">
//           <h2 className="text-2xl font-semibold">Welcome, {patient.name}</h2>
//         </div>

//         <div className="bg-white p-4 rounded shadow">
//           <p>Age: {patient.age}</p>
//           <p>Status: {patient.status}</p>
//         </div>

//         {/* Recordings Section */}
//         <div className="bg-white p-4 rounded shadow space-y-4">
//           <div className="flex justify-between items-center">
//             <h3 className="font-medium text-lg">Your Recordings</h3>
//             {/* <button
//               onClick={handleGenerateRecording}
//               disabled={analyzing}
//               className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded text-sm"
//             >
//               {analyzing ? 'Generating...' : 'Generate Recording'}
//             </button> */}
//           </div>

//           {recordings.length > 0 ? (
//             <div className="space-y-2">
//               {recordings.map((rec) => (
//                 <div
//                   key={rec.id}
//                   className="flex items-center justify-between bg-gray-50 p-2 rounded-md"
//                 >
//                   <span className="text-sm text-gray-700">{rec.label}</span>
//                   <button
//                     onClick={() => handleViewData(rec.id)}
//                     className="text-xs bg-indigo-600 hover:bg-indigo-700 text-white px-2 py-1 rounded"
//                   >
//                     View Data
//                   </button>
//                 </div>
//               ))}
//             </div>
//           ) : (
//             <div className="bg-yellow-50 border border-yellow-200 p-3 rounded text-sm text-gray-700 flex flex-col md:flex-row md:items-center md:justify-between gap-3">
//               <span>No recordings available for this patient.</span>
//               <button
//                 onClick={() => router.push('/patient/analysis')}
//                 className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded text-sm font-medium"
//               >
//                 Generate New Recording →
//               </button>
//             </div>
//           )}

//           {logs && (
//             <pre className="mt-4 max-h-64 overflow-auto text-xs bg-gray-100 p-3 rounded">{logs}</pre>
//           )}
//         </div>
//       </div>


// {/* Modal Visualization */}
// {showModal && selectedData && (
//   <div className="fixed inset-0 bg-black bg-opacity-40 flex items-center justify-center z-50">
//     {/* <div className="bg-white rounded-lg shadow-xl w-11/12 md:w-3/4 lg:w-2/3 p-6 relative"> */}
//   <div className="bg-white rounded-lg shadow-xl w-[95vw] max-w-[1400px] p-6 relative">

//       <button
//         onClick={closeModal}
//         className="absolute top-2 right-3 text-gray-500 hover:text-black"
//       >
//         ✕
//       </button>

//       <h3 className="text-xl font-semibold mb-6">{selectedData.label}</h3>

//       {(() => {
//         // Left leg data
//         // const leftAngles = selectedData.data.left_leg?.angles || []
//         const leftAngles = selectedData.angles?.left_leg?.angles || []

//         const leftData = leftAngles.map((a, i) => ({
//           time: i / 10,
//           angle: a,
//         }))

//         // Right leg data
//         // const rightAngles = selectedData.data.right_leg?.angles || []
//         const rightAngles = selectedData.angles?.right_leg?.angles || []

//         const rightData = rightAngles.map((a, i) => ({
//           time: i / 10,
//           angle: a,
//         }))

//         return (
//           <div className="flex flex-col  md:space-x-6 space-y-10 md:space-y-0">
//             {/* LEFT LEG */}
//             <div className="flex-1">
//               <h4 className="text-lg font-medium mb-2">Left Leg Angle vs Time</h4>
//               <div className="w-full h-64">
//                 <ResponsiveContainer width="100%" height="100%">
//                   <LineChart data={leftData}>
//                     <CartesianGrid strokeDasharray="3 3" />
//                     <XAxis dataKey="time" label={{ value: "Time (s)", position: "insideBottom" }} />
//                     <YAxis label={{ value: "Angle (°)", angle: -90, position: "insideLeft" }} />
//                     <Tooltip />
//                     <Line type="monotone" dataKey="angle" stroke="#1d4ed8" strokeWidth={2} dot={false} />
//                   </LineChart>
//                 </ResponsiveContainer>
//               </div>
//             </div>

//             {/* RIGHT LEG */}
//             <div className="flex-1">
//               <h4 className="text-lg font-medium mb-2">Right Leg Angle vs Time</h4>
//               <div className="w-full h-64">
//                 <ResponsiveContainer width="100%" height="100%">
//                   <LineChart data={rightData}>
//                     <CartesianGrid strokeDasharray="3 3" />
//                     <XAxis dataKey="time" label={{ value: "Time (s)", position: "insideBottom" }} />
//                     <YAxis label={{ value: "Angle (°)", angle: -90, position: "insideLeft" }} />
//                     <Tooltip />
//                     <Line type="monotone" dataKey="angle" stroke="#dc2626" strokeWidth={2} dot={false} />
//                   </LineChart>
//                 </ResponsiveContainer>
//               </div>
//             </div>
//           </div>
//         )
//       })()}
//     </div>
//   </div>
// )}


//     </Sidebar>
//   )
// }

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

  async function handleViewData(recId) {
    try {
      const res = await fetch(
        `${API_BASE}/recordings/${recId}?patient_name=${encodeURIComponent(patient?.name ?? "")}`
      )
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
        <h2 className="text-2xl font-semibold">Welcome, {patient.name}</h2>

        <div className="bg-white p-4 rounded shadow">
          <p>Age: {patient.age}</p>
          <p>Status: {patient.status}</p>
        </div>

        {/* Recordings Section */}
        <div className="bg-white p-4 rounded shadow space-y-4">
          <h3 className="font-medium text-lg">Your Recordings</h3>

          {recordings.length > 0 ? (
            <div className="space-y-2">
              {recordings.map((rec) => (
                <div key={rec.id} className="flex items-center justify-between bg-gray-50 p-2 rounded-md">
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
              <span>No recordings available.</span>
            </div>
          )}
        </div>
      </div>

{/* Modal Visualization */}
{showModal && selectedData && (
  <div className="fixed inset-0 bg-black bg-opacity-40 overflow-y-auto z-50 py-10">

    <div className="bg-white rounded-lg shadow-xl w-[95vw] max-w-[1400px] max-h-[90vh] overflow-y-auto p-6 relative mx-auto">

      <button
        onClick={closeModal}
        className="absolute top-2 right-3 text-gray-500 hover:text-black"
      >
        ✕
      </button>

      <h3 className="text-xl font-semibold mb-6">{selectedData.label}</h3>

      {/* ================= ANGLE CHARTS (OLD UI) ================= */}
      {(() => {

        // OLD GRAPH UI USES selectedData.angles
        const leftAngles = selectedData.angles?.left_leg?.angles || []
        const rightAngles = selectedData.angles?.right_leg?.angles || []

        const leftData = leftAngles.map((a, i) => ({
          time: i / 10,
          angle: a
        }))

        const rightData = rightAngles.map((a, i) => ({
          time: i / 10,
          angle: a
        }))

        return (
          <div className="flex flex-col md:space-x-6 space-y-10 md:space-y-0">
          {/* <div className="flex flex-col md:flex-row md:space-x-6 space-y-10 md:space-y-0"> */}

            {/* LEFT LEG GRAPH */}
            <div className="flex-1">
              <h4 className="text-lg font-medium mb-2">Left Leg Angle vs Time</h4>
              <div className="w-full h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={leftData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="time" label={{ value: "Time (s)", position: "insideBottom" }} />
                    <YAxis label={{ value: "Angle (°)", angle: -90, position: "insideLeft" }} />
                    <Tooltip />
                    <Line type="monotone" dataKey="angle" stroke="#1d4ed8" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* RIGHT LEG GRAPH */}
            <div className="flex-1">
              <h4 className="text-lg font-medium mb-2">Right Leg Angle vs Time</h4>
              <div className="w-full h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={rightData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="time" label={{ value: "Time (s)", position: "insideBottom" }} />
                    <YAxis label={{ value: "Angle (°)", angle: -90, position: "insideLeft" }} />
                    <Tooltip />
                    <Line type="monotone" dataKey="angle" stroke="#dc2626" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

          </div>
        )
      })()}

      {/* ================= GAIT REPORT ================= */}
      {selectedData.report && (
        <div className="mt-10 p-4 border rounded-lg bg-gray-50">
          <h3 className="text-xl font-semibold mb-4">Gait Report Summary</h3>

          {/* GLOBAL */}
          <div className="mb-6">
            <h4 className="text-lg font-medium mb-2">Global Metrics</h4>
            <pre className="text-sm bg-white p-3 rounded border overflow-auto">
{JSON.stringify(selectedData.report.global_metrics, null, 2)}
            </pre>
          </div>

          {/* LEFT LEG */}
          <div className="mb-6">
            <h4 className="text-lg font-medium mb-2">Left Leg Metrics</h4>
            <pre className="text-sm bg-white p-3 rounded border overflow-auto">
{JSON.stringify(selectedData.report.left_leg, null, 2)}
            </pre>
          </div>

          {/* RIGHT LEG */}
          <div className="mb-6">
            <h4 className="text-lg font-medium mb-2">Right Leg Metrics</h4>
            <pre className="text-sm bg-white p-3 rounded border overflow-auto">
{JSON.stringify(selectedData.report.right_leg, null, 2)}
            </pre>
          </div>

          {/* SYMMETRY */}
          {/* <div className="mb-6">
            <h4 className="text-lg font-medium mb-2">Symmetry Analysis</h4>
            <pre className="text-sm bg-white p-3 rounded border overflow-auto">
{JSON.stringify(selectedData.report.symmetry, null, 2)}
            </pre>
          </div> */}

          {/* STEP COORDINATION */}
          <div className="mb-6">
            <h4 className="text-lg font-medium mb-2">Step Coordination</h4>
            <pre className="text-sm bg-white p-3 rounded border overflow-auto">
{JSON.stringify(selectedData.report.step_coordination, null, 2)}
            </pre>
          </div>

          {/* INTER LIMB CORRELATION */}
          {/* <div className="mb-6">
            <h4 className="text-lg font-medium mb-2">Inter-Limb Correlation</h4>
            <pre className="text-sm bg-white p-3 rounded border overflow-auto">
{JSON.stringify(selectedData.report.inter_limb_correlation, null, 2)}
            </pre>
          </div> */}

          {/* CLINICAL INTERPRETATION */}
          {/* <div className="mb-6">
            <h4 className="text-lg font-medium mb-2">Clinical Interpretation</h4>
            <pre className="text-sm bg-white p-3 rounded border overflow-auto">
{JSON.stringify(selectedData.report.clinical_interpretation, null, 2)}
            </pre>
          </div> */}

        </div>
      )}

    </div>
  </div>
)}


    </Sidebar>
  )
}
