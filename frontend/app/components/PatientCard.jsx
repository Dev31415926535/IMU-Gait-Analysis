'use client'
import Link from 'next/link'


export default function PatientCard({ patient }) {
    return (
        <div className="bg-white p-4 rounded shadow">
            <div className="flex items-center justify-between">
                <div>
                    <h4 className="font-medium">{patient.name}</h4>
                    <p className="text-sm text-gray-500">ID: {patient.id}</p>
                </div>
                <Link href={`/admin/patient/${patient.id}`} className="text-indigo-600">Open</Link>
            </div>
        </div>
    )
}