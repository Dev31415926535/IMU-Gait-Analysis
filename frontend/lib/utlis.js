export const MOCK_PATIENTS = [
    { id: '1', name: 'Asha Kumar', age: 29, status: 'in-treatment', lastVisit: '2025-10-20', recordings: ['r1'] },
    { id: '2', name: 'Ravi Singh', age: 45, status: 'discharged', lastVisit: '2025-09-30', recordings: ['r2'] },
    { id: '3', name: 'Meera Patel', age: 36, status: 'in-treatment', lastVisit: '2025-10-18', recordings: ['r3'] },
]

export const MOCK_RECORDINGS = {
    r1: { id: 'r1', times: [0, 0.1, 0.2, 0.3, 0.4], angles: [45, 50, 62, 58, 48], metrics: { mean_knee_angle_deg: 52, detected_steps: 12 } },
    r2: { id: 'r2', times: [0, 0.1, 0.2], angles: [30, 28, 32], metrics: { mean_knee_angle_deg: 30, detected_steps: 2 } },
    r3: { id: 'r3', times: [0, 0.1, 0.2, 0.3], angles: [60, 62, 65, 63], metrics: { mean_knee_angle_deg: 62.5, detected_steps: 8 } }
}

export function useMockPatients() {
    return { data: MOCK_PATIENTS }
}

export const users = [
  { username: "admin", password: "admin", role: "admin" },
  { username: "John Doe", password: "123", role: "patient", patientId: "880f5383-a4e3-4a38-a13b-b59c17cfc1d6" },
  { username: "Jane Smith", password: "123", role: "patient", patientId: "7fd4e870-de98-4715-9f2c-abe7f6bb5adb" },
  { username: "dev", password: "123", role: "patient", patientId: "34589592-2c31-4343-ad16-b7801a90b09d" },
]
