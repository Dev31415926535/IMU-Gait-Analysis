'use client'
import Link from 'next/link'
import { Home, Folder, Activity, Settings, HelpCircle, LogOut } from 'lucide-react'

export default function Sidebar({ children }) {
  return (
    <div className="flex gap-6">
      <aside className="w-64 bg-white border rounded p-4 sticky top-6 h-[calc(100vh-4rem)] overflow-auto shadow-sm">
        <h3 className="font-semibold mb-4 text-lg text-gray-700">Navigation</h3>
        <ul className="space-y-2 text-sm text-gray-700">
          <li>
            <Link href="/admin" className="flex items-center gap-2 hover:text-blue-600">
              <Home size={16} /> Dashboard
            </Link>
          </li>
          <li>
            <Link href="/patient" className="flex items-center gap-2 hover:text-blue-600">
              <Folder size={16} /> My Recordings
            </Link>
          </li>
          <li>
            <Link href="/patient/analysis" className="flex items-center gap-2 hover:text-blue-600">
              <Activity size={16} /> Live Analysis
            </Link>
          </li>
          <li>
            <Link href="/settings" className="flex items-center gap-2 hover:text-blue-600">
              <Settings size={16} /> Settings
            </Link>
          </li>
          <li>
            <Link href="/help" className="flex items-center gap-2 hover:text-blue-600">
              <HelpCircle size={16} /> Help
            </Link>
          </li>
          {/* <li>
            <Link href="/login" className="flex items-center gap-2 text-red-600 hover:text-red-700 mt-4">
              <LogOut size={16} /> Logout
            </Link>
          </li> */}
        </ul>
      </aside>
      <div className="flex-1">{children}</div>
    </div>
  )
}