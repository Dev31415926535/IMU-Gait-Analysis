'use client'

import Link from 'next/link'
import { ArrowRight } from 'lucide-react'

export default function HomePage() {
  return (
    <div className="relative px-6 pt-10 lg:px-8">

      {/* Background decoration */}
      <div
        aria-hidden
        className="absolute inset-x-0 -top-40 -z-10 transform-gpu overflow-hidden blur-3xl sm:-top-80"
      >
        <div
          style={{
            clipPath:
              'polygon(74.1% 44.1%, 100% 61.6%, 97.5% 26.9%, 85.5% 0.1%, 80.7% 2%, 72.5% 32.5%, 60.2% 62.4%, 52.4% 68.1%, 47.5% 58.3%, 45.2% 34.5%, 27.5% 76.7%, 0.1% 64.9%, 17.9% 100%, 27.6% 76.8%, 76.1% 97.7%, 74.1% 44.1%)',
          }}
          className="relative left-[calc(50%-11rem)] aspect-[1155/678] w-[36rem]
          -translate-x-1/2 rotate-30 bg-gradient-to-tr from-pink-300
          to-indigo-400 opacity-30 sm:left-[calc(50%-30rem)] sm:w-[72rem]"
        />
      </div>

      {/* MAIN HERO CONTENT */}
      <div className="mx-auto max-w-3xl py-24 text-center sm:py-32 lg:py-40">
        <div className="sm:mb-8 sm:flex sm:justify-center">
          <div className="rounded-full px-3 py-1 text-sm text-gray-600 ring-1 ring-gray-900/10 hover:ring-gray-900/20">
            New: Live recording mode — smoother plots, lower latency.
            {/* <a href="#" className="ml-2 font-semibold text-indigo-600">
              See how →
            </a> */}
          </div>
        </div>

        <h1 className="text-4xl font-extrabold tracking-tight text-gray-900 sm:text-5xl">
          Physio Dashboard
        </h1>

        <p className="mt-4 text-lg text-gray-600">
          Real-time joint tracking, intuitive analytics, and easy patient management.
        </p>

        {/* BUTTONS */}
        <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:justify-center sm:items-center">
          <Link
            href="/admin"
            className="inline-flex items-center justify-center rounded-md bg-indigo-600 px-5 py-3 text-sm font-semibold text-white shadow hover:bg-indigo-500"
          >
            Admin Dashboard
            <ArrowRight className="ml-2" size={16} />
          </Link>

          <Link
            href="/patient"
            className="inline-flex items-center justify-center rounded-md border border-gray-200 px-5 py-3 text-sm font-semibold text-gray-700 bg-white shadow-sm hover:bg-gray-50"
          >
            Patient Dashboard
          </Link>
        </div>

        {/* Small Footer Line */}
        <div className="mt-10 text-sm text-gray-500">
          <strong className="font-medium text-gray-700">Get started:</strong> Connect your device, calibrate in 30s, and start recording.
        </div>
      </div>

      {/* Bottom gradient */}
      <div
        aria-hidden
        className="absolute inset-x-0 top-[calc(100%-13rem)] -z-10 transform-gpu overflow-hidden blur-3xl sm:top-[calc(100%-30rem)]"
      >
        <div
          style={{
            clipPath:
              'polygon(74.1% 44.1%, 100% 61.6%, 97.5% 26.9%, 85.5% 0.1%, 80.7% 2%, 72.5% 32.5%, 60.2% 62.4%, 52.4% 68.1%, 47.5% 58.3%, 45.2% 34.5%, 27.5% 76.7%, 0.1% 64.9%, 17.9% 100%, 27.6% 76.8%, 76.1% 97.7%, 74.1% 44.1%)',
          }}
          className="relative left-[calc(50%+3rem)] aspect-[1155/678]
          w-[36rem] -translate-x-1/2 bg-gradient-to-tr from-pink-300
          to-indigo-400 opacity-30 sm:left-[calc(50%+36rem)] sm:w-[72rem]"
        />
      </div>
    </div>
  )
}