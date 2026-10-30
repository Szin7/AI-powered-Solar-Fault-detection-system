'use client'

import { TrendingUp } from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, ResponsiveContainer, Tooltip, CartesianGrid, Legend } from 'recharts'
import { HistoryEntry } from '@/lib/types'

export function PowerOutputChart({ history, hardware = false }: { history: HistoryEntry[]; hardware?: boolean }) {
  const powers = history.map(h => h.power).filter((value): value is number => value != null && Number.isFinite(value))
  return (
    <div className="glass-card p-6">
      <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
        <TrendingUp className="w-5 h-5 text-solar-400" />
        {hardware ? 'Measured DC Power (V × I)' : 'Real-time AC Power Output'} (Up to 100 points)
      </h3>
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={history.slice(-100)}>
            <defs>
              <linearGradient id="powerGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#fbbf24" stopOpacity={0.5} />
                <stop offset="100%" stopColor="#fbbf24" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
            <XAxis
              dataKey="time"
              stroke="#64748b"
              fontSize={11}
              tick={{ fill: '#9ca3af' }}
              interval={Math.floor(history.length / 8)}
            />
            <YAxis
              stroke="#64748b"
              fontSize={11}
              tick={{ fill: '#9ca3af' }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#1f1f1f',
                border: '1px solid #fbbf24',
                borderRadius: '8px'
              }}
              formatter={(value) => [(value as number).toFixed(2) + ' W', 'Power']}
              labelStyle={{ color: '#9ca3af' }}
            />
            <Legend
              wrapperStyle={{ paddingTop: '20px' }}
              formatter={(name) => name === 'expected' ? 'Expected healthy AC (W)' : hardware ? 'DC voltage × current (W)' : 'Delivered AC (W)'}
            />
            <Area
              type="monotone"
              dataKey="power"
              stroke="#fbbf24"
              strokeWidth={3}
              fill="url(#powerGradient)"
              dot={{ fill: '#fbbf24', r: 3 }}
              activeDot={{ r: 6, fill: '#f59e0b' }}
            />
            {!hardware && <Area type="monotone" dataKey="expected" stroke="#22c55e" fill="transparent" strokeDasharray="5 5" />}
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-4 grid grid-cols-4 gap-2 text-center">
        <div className="p-2 rounded bg-white/5">
          <p className="text-xs text-gray-400">Total Points</p>
          <p className="text-lg font-bold text-yellow-400">{history.length}</p>
        </div>
        <div className="p-2 rounded bg-white/5">
          <p className="text-xs text-gray-400">Max Power</p>
          <p className="text-lg font-bold text-green-400">{powers.length ? Math.max(...powers).toFixed(1) : '—'} W</p>
        </div>
        <div className="p-2 rounded bg-white/5">
          <p className="text-xs text-gray-400">Min Power</p>
          <p className="text-lg font-bold text-blue-400">{powers.length ? Math.min(...powers).toFixed(1) : '—'} W</p>
        </div>
        <div className="p-2 rounded bg-white/5">
          <p className="text-xs text-gray-400">Avg Power</p>
          <p className="text-lg font-bold text-purple-400">
            {powers.length ? (powers.reduce((a, b) => a + b, 0) / powers.length).toFixed(1) : '—'} W
          </p>
        </div>
      </div>
    </div>
  )
}
