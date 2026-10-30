'use client'

import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, AreaChart, Area, Tooltip, CartesianGrid, Legend } from 'recharts'
import { HistoryEntry } from '@/lib/types'

export function MiniChart({ data, dataKey, color, title }: {
  data: HistoryEntry[]
  dataKey: string
  color: string
  title: string
}) {
  const [showDetail, setShowDetail] = useState(false)

  const values = data.map(row => (row as any)[dataKey]).filter((value): value is number => typeof value === 'number' && Number.isFinite(value))
  const fmt = (value: unknown) => typeof value === 'number' && Number.isFinite(value) ? value.toFixed(3) : '—'
  return (
    <>
      <motion.div
        onClick={() => setShowDetail(true)}
        className="glass-card p-4 cursor-pointer hover:border-white/20 transition-all hover:scale-105"
        whileHover={{ scale: 1.02 }}
      >
        <h4 className="text-sm font-medium text-gray-400 mb-2 flex items-center justify-between">
          <span>{title}</span>
          <span className="text-xs px-2 py-1 rounded bg-white/10 text-white/60">Click to expand</span>
        </h4>
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data.slice(-100)}>
              <defs>
                <linearGradient id={`gradient-${dataKey}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={color} stopOpacity={0.4} />
                  <stop offset="100%" stopColor={color} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
              <XAxis
                dataKey="time"
                tick={{ fontSize: 10, fill: '#9ca3af' }}
                interval={Math.floor(data.length / 5)}
              />
              <YAxis
                tick={{ fontSize: 10, fill: '#9ca3af' }}
                width={40}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1f1f1f',
                  border: `1px solid ${color}`,
                  borderRadius: '8px'
                }}
                formatter={(value) => (value as number).toFixed(2)}
                labelStyle={{ color: '#9ca3af' }}
              />
              <Area
                type="monotone"
                dataKey={dataKey}
                stroke={color}
                strokeWidth={2}
                fill={`url(#gradient-${dataKey})`}
                dot={{ fill: color, r: 3 }}
                activeDot={{ r: 5 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-2 text-xs text-gray-500 text-center">
          Points: {data.length} | Latest: {data.length > 0 ? (data[data.length - 1] as any)[dataKey]?.toFixed(2) : 'N/A'}
        </div>
      </motion.div>

      {/* Detailed Modal */}
      <AnimatePresence>
        {showDetail && (
          <motion.div
            className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setShowDetail(false)}
          >
            <motion.div
              className="bg-dark-800 border border-white/20 rounded-2xl p-8 max-w-5xl w-full max-h-[90vh] overflow-y-auto"
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-2xl font-bold flex items-center gap-3">
                  <div className="w-4 h-4 rounded" style={{ backgroundColor: color }} />
                  {title} - Detailed Analysis
                </h2>
                <motion.button
                  onClick={() => setShowDetail(false)}
                  className="p-2 hover:bg-white/10 rounded-lg transition-all"
                  whileHover={{ scale: 1.1 }}
                >
                  ✕
                </motion.button>
              </div>

              {/* Large Chart */}
              <div className="mb-8 p-6 rounded-xl bg-white/5 border border-white/10">
                <h3 className="text-lg font-semibold mb-4 text-gray-300">100-Point History</h3>
                <div className="h-96">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={data.slice(-100)}>
                      <defs>
                        <linearGradient id={`detail-gradient-${dataKey}`} x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor={color} stopOpacity={0.3} />
                          <stop offset="100%" stopColor={color} stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.15)" />
                      <XAxis
                        dataKey="time"
                        tick={{ fontSize: 12, fill: '#9ca3af' }}
                        interval={Math.max(0, Math.floor(data.length / 12))}
                      />
                      <YAxis
                        tick={{ fontSize: 12, fill: '#9ca3af' }}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#1f2937',
                          border: `2px solid ${color}`,
                          borderRadius: '12px',
                          padding: '12px'
                        }}
                        formatter={(value, name) => [(value as number).toFixed(3), 'Value']}
                        labelFormatter={(label) => `Time: ${label}`}
                        labelStyle={{ color: '#f3f4f6' }}
                      />
                      <Legend wrapperStyle={{ paddingTop: '20px' }} />
                      <Line
                        type="monotone"
                        dataKey={dataKey}
                        stroke={color}
                        strokeWidth={3}
                        dot={{ fill: color, r: 4 }}
                        activeDot={{ r: 7, fill: color }}
                        name={title}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Statistics */}
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-8">
                <div className="p-4 rounded-lg bg-green-500/10 border border-green-500/30">
                  <p className="text-xs text-gray-400 mb-1">Maximum</p>
                  <p className="text-2xl font-bold text-green-400">
                    {data.length > 0 ? values.length ? Math.max(...values).toFixed(3) : '—' : 'N/A'}
                  </p>
                </div>
                <div className="p-4 rounded-lg bg-blue-500/10 border border-blue-500/30">
                  <p className="text-xs text-gray-400 mb-1">Minimum</p>
                  <p className="text-2xl font-bold text-blue-400">
                    {data.length > 0 ? values.length ? Math.min(...values).toFixed(3) : '—' : 'N/A'}
                  </p>
                </div>
                <div className="p-4 rounded-lg bg-purple-500/10 border border-purple-500/30">
                  <p className="text-xs text-gray-400 mb-1">Average</p>
                  <p className="text-2xl font-bold text-purple-400">
                    {data.length > 0 ? values.length ? (values.reduce((a, b) => a + b, 0) / values.length).toFixed(3) : '—' : 'N/A'}
                  </p>
                </div>
                <div className="p-4 rounded-lg bg-yellow-500/10 border border-yellow-500/30">
                  <p className="text-xs text-gray-400 mb-1">Current</p>
                  <p className="text-2xl font-bold text-yellow-400">
                    {data.length > 0 ? (data[data.length - 1] as any)[dataKey]?.toFixed(3) : 'N/A'}
                  </p>
                </div>
                <div className="p-4 rounded-lg bg-red-500/10 border border-red-500/30">
                  <p className="text-xs text-gray-400 mb-1">Total Points</p>
                  <p className="text-2xl font-bold text-red-400">{data.length}</p>
                </div>
              </div>

              {/* Data Table */}
              <div className="mb-8">
                <h3 className="text-lg font-semibold mb-3 text-gray-300">Data Points (Last 20 entries)</h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-white/10">
                        <th className="px-4 py-2 text-left text-gray-400">#</th>
                        <th className="px-4 py-2 text-left text-gray-400">Time</th>
                        <th className="px-4 py-2 text-left" style={{ color }}>{title}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.slice(-20).map((row, idx) => (
                        <tr key={idx} className="border-b border-white/5 hover:bg-white/5 transition">
                          <td className="px-4 py-2 text-gray-500">{Math.max(0, data.length - 20) + idx + 1}</td>
                          <td className="px-4 py-2 text-gray-300">{row.time}</td>
                          <td className="px-4 py-2 font-semibold" style={{ color }}>
                            {fmt((row as any)[dataKey])}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Close Button */}
              <motion.button
                onClick={() => setShowDetail(false)}
                className="w-full p-3 rounded-lg bg-gradient-to-r from-solar-500 to-solar-600 text-white font-semibold hover:from-solar-600 hover:to-solar-700 transition-all"
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                Close Detailed View
              </motion.button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
