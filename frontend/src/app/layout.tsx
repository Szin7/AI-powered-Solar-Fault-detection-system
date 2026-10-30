import type { Metadata } from 'next'
import './globals.css'


export const metadata: Metadata = {
  title: 'Solar Panel Fault Detection | Solar Monitoring',
  description: 'Real-time ML-powered fault detection system for solar panels using Random Forest algorithm',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  )
}
