'use client'

import { TrendingUp } from 'lucide-react'
import { MiniChart } from '@/components/MiniChart'
import { HistoryEntry } from '@/lib/types'

// Grid of expandable mini-charts, one per sensor channel (up to 100 points each).
export function SensorHistoryCharts({ history }: { history: HistoryEntry[] }) {
  return (
    <div className="mb-6">
      <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
        <TrendingUp className="w-5 h-5 text-solar-400" />
        Sensor History Charts (Up to 100 points)
      </h3>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <MiniChart data={history} dataKey="power" color="#fbbf24" title="Power Output (W)" />
        <MiniChart data={history} dataKey="voltage" color="#3b82f6" title="Voltage (V)" />
        <MiniChart data={history} dataKey="current" color="#ef4444" title="Current (A)" />
        <MiniChart data={history} dataKey="temperature" color="#f59e0b" title="Temperature (°C)" />
        <MiniChart data={history} dataKey="light" color="#22c55e" title="Light (ADC)" />
        <MiniChart data={history} dataKey="irradiance" color="#8b5cf6" title="Irradiance (W/m²)" />
        <MiniChart data={history} dataKey="humidity" color="#06b6d4" title="Humidity (%)" />
        <MiniChart data={history} dataKey="thermistor" color="#ec4899" title="Panel Temperature (°C)" />
      </div>
    </div>
  )
}
