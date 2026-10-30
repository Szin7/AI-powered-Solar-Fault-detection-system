'use client'

import { motion } from 'framer-motion'
import { Battery, Activity } from 'lucide-react'
import { Prediction } from '@/lib/types'
import { FAULT_INFO } from '@/lib/constants'

export function StatusCard({ prediction }: { prediction: Prediction | null }) {
  if (!prediction) return null

  const info = FAULT_INFO[prediction.fault_type] || { gradient: 'from-slate-600 to-slate-700', icon: '?', description: 'No confirmed fault classification for this reading' }

  return (
    <motion.div
      className={`glass-card p-8 border-2 ${prediction.is_fault ? 'status-fault' : prediction.fault_type === 'Normal' ? 'status-normal' : 'border-white/20'}`}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      key={prediction.fault_type}
    >
      <div className="flex flex-wrap gap-4 items-center justify-between">
        <div className="flex items-center gap-4">
          <motion.div
            className={`w-20 h-20 rounded-2xl bg-gradient-to-br ${info.gradient} flex items-center justify-center text-4xl`}
            animate={prediction.is_fault ? { scale: [1, 1.1, 1] } : {}}
            transition={{ repeat: Infinity, duration: 1 }}
          >
            {info.icon}
          </motion.div>
          <div>
            <h2 className="text-3xl font-bold">{prediction.fault_type.replaceAll('_', ' ')}</h2>
            <p className="text-gray-400 mt-1">{info.description}</p>
          </div>
        </div>
        <div className="text-right">
          <div className="text-5xl font-bold gradient-text">{Number.isFinite(prediction.confidence) ? prediction.confidence.toFixed(1) + '%' : '—'}</div>
          <div className="text-gray-400 mt-1">{['raw_forest', 'original_raw_forest'].includes(prediction.probability_method ?? '') ? 'Model score (uncalibrated)' : 'Model confidence'}</div>
        </div>
      </div>

      <div className="mt-6 flex flex-wrap gap-4">
        <div className="flex items-center gap-2">
          <Battery className="w-5 h-5 text-solar-400" />
          <span className="text-gray-300">Power Output:</span>
          <span className="font-bold text-white">{Number.isFinite(prediction.power) ? prediction.power.toFixed(1) : '—'} W</span>
        </div>
        <div className="flex items-center gap-2">
          <Activity className="w-5 h-5 text-green-400" />
          <span className="text-gray-300">Status:</span>
          <span className={`font-bold ${prediction.is_fault ? 'text-red-400' : prediction.fault_type === 'Normal' ? 'text-green-400' : 'text-gray-300'}`}>
            {prediction.is_fault ? 'FAULT DETECTED' : prediction.fault_type === 'Normal' ? 'OPERATIONAL' : 'AWAITING VALID DECISION'}
          </span>
        </div>
      </div>
    </motion.div>
  )
}
