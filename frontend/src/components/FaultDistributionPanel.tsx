'use client'

import { AlertTriangle } from 'lucide-react'
import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts'
import { FAULT_INFO } from '@/lib/constants'

export function FaultDistributionPanel({ faultCounts }: { faultCounts: Record<string, number> }) {
  const pieData = Object.entries(faultCounts).map(([name, value]) => ({
    name,
    value,
    color: FAULT_INFO[name]?.color || '#666'
  }))

  return (
    <div className="glass-card p-6">
      <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
        <AlertTriangle className="w-5 h-5 text-solar-400" />
        Fault Distribution
      </h3>
      {pieData.length > 0 ? (
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={pieData}
                cx="50%"
                cy="50%"
                innerRadius={40}
                outerRadius={70}
                dataKey="value"
                stroke="none"
              >
                {pieData.map((entry, index) => (
                  <Cell key={index} fill={entry.color} />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="h-48 flex items-center justify-center text-gray-500">
          Start monitoring to see distribution
        </div>
      )}
      <div className="mt-4 space-y-2">
        {Object.entries(FAULT_INFO).map(([name, info]) => (
          <div key={name} className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full" style={{ backgroundColor: info.color }} />
              <span className="text-gray-300">{name.replace('_', ' ')}</span>
            </div>
            <span className="font-medium">{faultCounts[name] || 0}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
