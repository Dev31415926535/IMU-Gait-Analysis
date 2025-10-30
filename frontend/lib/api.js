import axios from 'axios'
import { MOCK_PATIENTS, MOCK_RECORDINGS } from './utlis'

const base = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000'
const api = axios.create({ baseURL: base, timeout: 6000 })

async function safeGet(path) {
    try {
        const res = await api.get(path)
        return res.data
    } catch (e) {
        console.error('API GET failed', path, e.message)
        throw e
    }
}

export async function fetchPatients() {
    try {
        return await safeGet('/patients')
    } catch (e) {
        // fallback
        return MOCK_PATIENTS
    }
}

export async function fetchPatient(id) {
    try { return await safeGet(`/patients/${id}`) } catch (e) {
        return MOCK_PATIENTS.find(p => p.id === id) || null
    }
}

export async function createPatient(payload) {
    try { const res = await api.post('/patients', payload); return res.data } catch (e) {
        console.error('Create failed, returning mock created object', e.message)
        const newPatient = { id: String(Date.now()), ...payload }
        MOCK_PATIENTS.push(newPatient)
        return newPatient
    }
}

export async function updatePatient(id, payload) {
    try { const res = await api.put(`/patients/${id}`, payload); return res.data } catch (e) {
        const p = MOCK_PATIENTS.find(x => x.id === id)
        if (p) Object.assign(p, payload)
        return p
    }
}

export async function deletePatient(id) {
    try { await api.delete(`/patients/${id}`); return { ok: true } } catch (e) {
        const idx = MOCK_PATIENTS.findIndex(x => x.id === id); if (idx >= 0) MOCK_PATIENTS.splice(idx, 1)
        return { ok: true }
    }
}

export async function fetchRecording(id) {
  const res = await api.get(`/recordings/${id}`)
  return res.data
}

// 🔹 Run new analysis (rehab/new patient)
export async function runAnalysis(patientId) {
  const res = await api.post(`/analyze/${patientId}`)
  return res.data
}
