import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import Navbar from '@/app/components/Navbar'
import { AuthProvider } from '@/app/components/AuthProvider'

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata = {
title: 'Physio Dashboard',
description: 'Admin + Patient dashboards for IMU physiotherapy data',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className="bg-gray-50 text-gray-800">
        <AuthProvider>
          <Navbar />
          <main className="p-6 max-w-7xl mx-auto">{children}</main>
        </AuthProvider>
      </body>
    </html>
  );
}
