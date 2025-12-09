import AngleChart from '@/app/components/AngleChart'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function formatTimestamp(ts) {
    if (!ts) return "Unknown"

    // backend format: "2025-11-15_105405"
    const [date, time] = ts.split("_")   // ["2025-11-15", "105405"]
    const formatted = date + " " +
        `${time.slice(0,2)}:${time.slice(2,4)}:${time.slice(4,6)}`

    return new Date(formatted).toLocaleString()
}

/**
 * Fetch a patient by id.
 * Calls: GET /patients/{id}
 * Returns: patient object (may include .recordings if backend attaches them)
 */
async function fetchPatient(id) {
  if (!id) throw new Error("fetchPatient: missing id");

  const url = `${API_BASE}/patients/${encodeURIComponent(id)}`;

  const res = await fetch(url, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`fetchPatient failed (${res.status}): ${text}`);
  }

  const data = await res.json();
  return data;
}

/**
 * Fetch a recording by its id.
 * Calls: GET /recordings/{rid}?patient_name=...
 *
 * @param {string} recId  The recording id (example: "2025-11-15_10-52-57_bilateral_metrics_...")
 * @param {string} [patientName] optional patient name (recommended because backend expects it)
 * @returns {object} { id, angles, report } as returned by backend
 */
async function fetchRecording(recId, patientName = null) {
  if (!recId) throw new Error("fetchRecording: missing recId");

  // attach patient_name query param if provided
  const q = patientName ? `?patient_name=${encodeURIComponent(patientName)}` : "";
  const url = `${API_BASE}/recordings/${encodeURIComponent(recId)}${q}`;

  const res = await fetch(url, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });

  // If the backend requires patient_name and we didn't provide it, try a helpful retry
  if (res.status === 422 && !patientName) {
    throw new Error("fetchRecording: backend requires patient_name query parameter");
  }

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`fetchRecording failed (${res.status}): ${text}`);
  }

  const data = await res.json();
  return data;
}

export default async function AdminPatientPage({ params }) {
    const { id } = params

    // --------------------------------------------------------
    // 1) Fetch Patient
    // --------------------------------------------------------
    let patient = null
    try {
        patient = await fetchPatient(id)
    } catch (e) {
        patient = {
            id,
            name: `Patient ${id}`,
            recordings: [{ id: 'r1', label: 'Session 1' }]
        }
    }

    // const latestRecId = patient.recordings?.[0]?.id || 'r1'
    const latestRec = patient.recordings?.[0]
    const latestRecId = latestRec?.id || 'r1'
    const latestTimestamp = latestRec?.timestamp || null


    // --------------------------------------------------------
    // 2) Fetch latest bilateral recording preview
    // Expected from API:
    // {
    //    angles: {
    //        left_leg: { angles: [...] },
    //        right_leg: { angles: [...] }
    //    },
    //    report: { left_leg: {...}, right_leg: {...} }
    // }
    // --------------------------------------------------------
    let recording
    try {
        recording = await fetchRecording(latestRecId, patient.name)
    } catch (e) {
        // fallback demo data
        recording = {
            angles: {
                left_leg: { angles: [45, 50, 60, 55] },
                right_leg: { angles: [40, 48, 62, 57] }
            },
            report: {
                left_leg: { detected_steps: 21, knee_rom_deg: 22, cadence_spm: 100, peak_knee_angle_deg: 110 },
                right_leg: { detected_steps: 22, knee_rom_deg: 24, cadence_spm: 102, peak_knee_angle_deg: 112 }
            }
        }
    }

    // --------------------------------------------------------
    // 3) Build preview chart using LEFT LEG only (most common)
    // --------------------------------------------------------
    const preview = recording.angles?.left_leg?.angles || []
    const chartData = preview.map((a, i) => ({
        time_s: i / 10,
        angle_deg: a
    }))

    return (
        <div className="space-y-4">
            <h2 className="text-2xl font-semibold">
                {patient.name} — Admin View
            </h2>

            <div className="grid grid-cols-3 gap-4">
                {/* -------- LEFT LEG PREVIEW GRAPH -------- */}
                <div className="col-span-2">
                    <AngleChart data={chartData} />
                </div>

                {/* -------- SESSION METRICS PREVIEW -------- */}
                <div className="bg-white p-4 rounded shadow">
                    <h4 className="font-medium mb-2">Latest Session Metrics</h4>

                    <div className="text-sm">
                        <h5 className="font-semibold">Left Leg</h5>
                        <p>Steps: {recording?.report?.left_leg?.detected_steps ?? '—'}</p>
                        <p>ROM: {recording?.report?.left_leg?.knee_rom_deg ?? '—'}°</p>
                        <p>Cadence: {recording?.report?.left_leg?.cadence_spm ?? '—'} spm</p>
                        <p>Peak Angle: {recording?.report?.left_leg?.peak_knee_angle_deg ?? '—'}°</p>

                        <div className="mt-3" />

                        <h5 className="font-semibold">Right Leg</h5>
                        <p>Steps: {recording?.report?.right_leg?.detected_steps ?? '—'}</p>
                        <p>ROM: {recording?.report?.right_leg?.knee_rom_deg ?? '—'}°</p>
                        <p>Cadence: {recording?.report?.right_leg?.cadence_spm ?? '—'} spm</p>
                        <p>Peak Angle: {recording?.report?.right_leg?.peak_knee_angle_deg ?? '—'}°</p>
                    </div>
                </div>
            </div>
        </div>
    )
}
