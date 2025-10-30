"use client"
export default function AdminError({ error }) {
    return (
        <div className="p-6">
            <h2 className="text-xl font-semibold">Something went wrong</h2>
            <p className="text-gray-600">Unable to load admin data. {String(error?.message || '')}</p>
        </div>
    )
}