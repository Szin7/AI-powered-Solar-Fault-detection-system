'use client'

import { motion } from 'framer-motion'

export function Gauge({ value, min, max, label, unit, color, icon: Icon }: {
  value: number | null
  min: number
  max: number
  label: string
  unit: string
  color: string
  icon: any
}) {
  const percentage = Math.min(100, Math.max(0, (((value ?? min) - min) / (max - min)) * 100))
  const circumference = 2 * Math.PI * 45
  const strokeDasharray = `${(percentage / 100) * circumference} ${circumference}`

  return (
    <motion.div
      className="glass-card p-4 flex flex-col items-center"
      whileHover={{ scale: 1.02 }}
      transition={{ type: "spring", stiffness: 300 }}
    >
      <div className="relative w-28 h-28 md:w-32 md:h-32">
        <svg className="w-full h-full -rotate-90" viewBox="0 0 100 100">
          {/* Background circle */}
          <circle
            cx="50"
            cy="50"
            r="45"
            stroke="rgba(255,255,255,0.1)"
            strokeWidth="8"
            fill="none"
          />
          {/* Progress circle */}
          <motion.circle
            cx="50"
            cy="50"
            r="45"
            stroke={color}
            strokeWidth="8"
            fill="none"
            strokeLinecap="round"
            initial={{ strokeDasharray: `0 ${circumference}` }}
            animate={{ strokeDasharray }}
            transition={{ duration: 0.5, ease: "easeOut" }}
            style={{ filter: `drop-shadow(0 0 10px ${color})` }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <Icon className="w-5 h-5 mb-1" style={{ color }} />
          <span className="text-2xl font-bold">{value != null && Number.isFinite(value) ? value.toFixed(1) : '—'}</span>
          <span className="text-xs text-gray-400">{unit}</span>
        </div>
      </div>
      <span className="mt-3 text-sm font-medium text-gray-300">{label}</span>
    </motion.div>
  )
}
