'use client'
import { useAuth } from './AuthProvider'
import { useRouter } from 'next/navigation'
import { useEffect } from 'react'

export default function Protected({ children, role = 'admin' }) {
    const { user } = useAuth()
    const router = useRouter()
    useEffect(() => {
        if (user === null) { router.replace('/login') }
        else if (role && user?.role !== role) {
            // unauthorized
            router.replace('/')
        }
    }, [user])

    if (!user) return null
    if (role && user.role !== role) return null
    return children
}