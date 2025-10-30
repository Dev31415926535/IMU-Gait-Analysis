//No 'use client' here — this is a SERVER component by default
import Protected from '@/app/components/Protected'
import AdminClient from './AdminClient' // import client component
import { fetchPatients } from '@/lib/api'

export default async function AdminPage() {
  let patients = []
  try {
    patients = await fetchPatients()
  } catch {
    patients = []
  }

  return (
    <Protected>
      <AdminClient initialPatients={patients} />
    </Protected>
  )
}
