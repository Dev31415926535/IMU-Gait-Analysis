import Link from 'next/link'

export default function HomePage() {
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-semibold">Welcome — Physio Dashboard</h1>
      <p className="text-gray-600">Choose a portal to continue.</p>
      <div className="flex gap-4">
        <Link href="/admin" className="px-6 py-4 bg-indigo-600 text-white rounded shadow">Admin Dashboard</Link>
        <Link href="/patient" className="px-6 py-4 bg-green-600 text-white rounded shadow">Patient Dashboard</Link>
      </div>
    </div>
  )
}