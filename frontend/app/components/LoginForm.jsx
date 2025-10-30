'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from './AuthProvider'

export default function LoginForm() {
    const [username, setUsername] = useState('')
    const [password, setPassword] = useState('')
    const [err, setErr] = useState(null)
    const { login } = useAuth()
    const router = useRouter()

    function onSubmit(e) {
    e.preventDefault()
    if (!username || !password) return setErr('Enter username and password')
    try {
        const u = login({ username, password })
        if (u.role === 'admin') router.push('/admin')
        else router.push('/patient')
    } catch (error) {
        setErr(error.message)
    }
    }

    return (
        <form onSubmit={onSubmit} className="max-w-md bg-white p-6 rounded shadow space-y-3">
            <h3 className="text-lg font-semibold">Sign in</h3>
            {err && <div className="text-red-600">{err}</div>}
            <input value={username} onChange={e => setUsername(e.target.value)} placeholder="username" className="w-full p-2 border rounded" />
            <input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="password" className="w-full p-2 border rounded" />
            <div className="flex justify-between items-center">
                <button className="px-4 py-2 bg-indigo-600 text-white rounded">Login</button>
                <small className="text-gray-500">Use admin/admin for admin</small>
            </div>
        </form>
    )
}