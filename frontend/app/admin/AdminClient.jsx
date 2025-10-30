'use client'
import { useEffect, useState } from 'react'
import Sidebar from '@/app/components/Sidebar'
import PatientCard from '@/app/components/PatientCard'
import StatsPanel from '@/app/components/StatsPanel'
import PatientManageForm from '@/app/components/PatientManageForm'
import { fetchPatients, createPatient, updatePatient, deletePatient } from '@/lib/api'
import Link from 'next/link'

export default function AdminClient({ initialPatients }) {
  const [patients, setPatients] = useState(initialPatients || [])
  const [q, setQ] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [editing, setEditing] = useState(null)
  const [showCreate, setShowCreate] = useState(false)

  const filtered = patients.filter(p =>
    p.name.toLowerCase().includes(q.toLowerCase()) &&
    (statusFilter ? p.status === statusFilter : true)
  )

  useEffect(() => {
    async function loadPatients() {
      try {
        const data = await fetchPatients()
        setPatients(data)
      } catch (err) {
        console.error('Failed to load patients', err)
      }
    }
    loadPatients()
  }, [])

  async function handleCreate(payload) {
    const created = await createPatient(payload)
    setPatients(s => [...s, created])
    setShowCreate(false)
  }

  async function handleUpdate(id, payload) {
    const updated = await updatePatient(id, payload)
    setPatients(s => s.map(x => x.id === id ? updated : x))
    setEditing(null)
  }

  async function handleDelete(id) {
    await deletePatient(id)
    setPatients(s => s.filter(x => x.id !== id))
  }

  return (
    <Sidebar>
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-2xl font-semibold">Admin Dashboard</h2>
          <div className="flex gap-2">
            <button onClick={() => setShowCreate(s => !s)} className="px-3 py-2 bg-green-600 text-white rounded">
              New Patient
            </button>
          </div>
        </div>

        <StatsPanel patients={patients} />

        <div className="bg-white p-4 rounded shadow">
          <div className="flex gap-2 mb-3">
            <input
              value={q}
              onChange={e => setQ(e.target.value)}
              placeholder="Search by name"
              className="p-2 border rounded flex-1"
            />
            <select
              value={statusFilter}
              onChange={e => setStatusFilter(e.target.value)}
              className="p-2 border rounded"
            >
              <option value="">All statuses</option>
              <option value="in-treatment">in-treatment</option>
              <option value="discharged">discharged</option>
              <option value="pending">pending</option>
            </select>
          </div>

          {showCreate && (
            <PatientManageForm onSave={handleCreate} onCancel={() => setShowCreate(false)} />
          )}

          <div className="grid grid-cols-2 gap-4 mt-4">
            {filtered.map(p => (
              <div key={p.id} className="bg-gray-50 p-3 rounded border">
                <div className="flex justify-between items-start">
                  <div>
                    <div className="font-medium">{p.name}</div>
                    <div className="text-sm text-gray-500">Age: {p.age} • {p.status}</div>
                  </div>
                  <div className="flex flex-col gap-2">
                    <button onClick={() => setEditing(p)} className="text-indigo-600 text-sm">Edit</button>
                    <button onClick={() => handleDelete(p.id)} className="text-red-600 text-sm">Delete</button>
                  </div>
                </div>
                <div className="mt-2 text-sm">
                  Last visit: {p.lastVisit}
                </div>
                {/* 👇 Add your "View Info" button here */}
                <div className="mt-3">
                  <Link
                    href={`/admin/patient/${p.id}`}
                    className="inline-block bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium px-3 py-1 rounded"
                  >
                    View Patient Info
                  </Link>
                </div>
              </div>
            ))}
          </div>

          {editing && (
            <div className="mt-4">
              <h4 className="font-medium">Edit patient</h4>
              <PatientManageForm
                initial={editing}
                onSave={(data) => handleUpdate(editing.id, data)}
                onCancel={() => setEditing(null)}
              />
            </div>
          )}
        </div>
      </div>
    </Sidebar>
  )
}