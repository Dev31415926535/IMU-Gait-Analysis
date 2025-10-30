'use client'
import { useState } from 'react'

export default function PatientManageForm({ initial = {}, onSave, onCancel }) {
    const [form, setForm] = useState({ name: initial.name || '', age: initial.age || '', status: initial.status || 'in-treatment' })
    function update(k, v) { setForm(s => ({ ...s, [k]: v })) }
    return (
        <form onSubmit={e => { e.preventDefault(); onSave(form) }} className="space-y-3 bg-white p-4 rounded shadow">
            <div>
                <label className="text-sm">Name</label>
                <input value={form.name} onChange={e => update('name', e.target.value)} className="w-full p-2 border rounded" />
            </div>
            <div>
                <label className="text-sm">Age</label>
                <input type="number" value={form.age} onChange={e => update('age', Number(e.target.value))} className="w-full p-2 border rounded" />
            </div>
            <div>
                <label className="text-sm">Status</label>
                <select value={form.status} onChange={e => update('status', e.target.value)} className="w-full p-2 border rounded">
                    <option value="in-treatment">in-treatment</option>
                    <option value="discharged">discharged</option>
                    <option value="pending">pending</option>
                </select>
            </div>
            <div className="flex gap-2">
                <button className="px-3 py-2 bg-indigo-600 text-white rounded">Save</button>
                <button type="button" onClick={onCancel} className="px-3 py-2 border rounded">Cancel</button>
            </div>
        </form>
    )
}