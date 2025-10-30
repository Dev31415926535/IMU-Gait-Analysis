import Sidebar from '@/app/components/Sidebar'
import AngleChart from '@/app/components/AngleChart'
import { fetchPatient, fetchRecording } from '@/lib/api'

export default async function AdminPatientPage({ params }) {
    const { id } = params
    let patient = null
    try { patient = await fetchPatient(id) } catch (e) { patient = { id, name: `Patient ${id}`, recordings: [{ id: 'r1', label: 'Session 1' }] } }

    // fetch latest recording data for preview
    let recording = null
    try { recording = await fetchRecording(patient.recordings?.[0]?.id || 'r1') } catch (e) {
        // demo recording format expected: { times: [...], angles: [...] }
        recording = { times: [0, 0.1, 0.2, 0.3], angles: [45, 50, 60, 55], metrics: { mean_knee_angle_deg: 52 } }
    }

    const chartData = (recording.times || []).map((t, i) => ({ time_s: t, angle_deg: recording.angles?.[i] ?? null }))

    return (
        <Sidebar>
            <div className="space-y-4">
                <h2 className="text-2xl font-semibold">{patient.name} — Admin View</h2>

                <div className="grid grid-cols-3 gap-4">
                    <div className="col-span-2">
                        <AngleChart data={chartData} />
                    </div>
                    <div className="bg-white p-4 rounded shadow">
                        <h4 className="font-medium">Session Metrics</h4>
                        <p>Mean knee angle: {recording.metrics?.mean_knee_angle_deg ?? '—'}</p>
                        <p>Detected steps: {recording.metrics?.detected_steps ?? '—'}</p>
                    </div>
                </div>
            </div>
        </Sidebar>
    )
}