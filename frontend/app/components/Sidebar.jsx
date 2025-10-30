'use client'
import Link from 'next/link'


export default function Sidebar({ children }) {
    return (
        <div className="flex gap-6">
            <aside className="w-64 bg-white border rounded p-4 sticky top-6 h-[calc(100vh-4rem)] overflow-auto">
                <h3 className="font-semibold mb-3">Menu</h3>
                <ul className="space-y-2 text-sm">
                    <li><Link href="/admin">Dashboard</Link></li>
                    <li><Link href="/admin/patient/1">Patient Example</Link></li>
                    <li><Link href="/patient">My Records</Link></li>
                </ul>
            </aside>
            <div className="flex-1">{children}</div>
        </div>
    )
}