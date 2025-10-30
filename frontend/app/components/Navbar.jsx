'use client'
import Link from 'next/link'
import { useAuth } from './AuthProvider'

export default function Navbar() {
    const { user, logout } = useAuth() || {}
    return (
        <nav className="bg-white border-b">
            <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="w-9 h-9 bg-indigo-600 rounded flex items-center justify-center text-white font-bold">PH</div>
                    <span className="font-semibold">Physio Dashboard</span>
                </div>
                <div className="flex items-center gap-3">
                    <Link href="/admin" className="text-sm text-gray-600">Admin</Link>
                    <Link href="/patient" className="text-sm text-gray-600">Patient</Link>
                    {user ? (
                        <div className="flex items-center gap-2">
                            <span className="text-sm text-gray-700">{user.username} ({user.role})</span>
                            <button onClick={logout} className="text-sm text-red-600">Logout</button>
                        </div>
                    ) : (
                        <Link href="/login" className="text-sm text-gray-600">Login</Link>
                    )}
                </div>
            </div>
        </nav>
    )
}