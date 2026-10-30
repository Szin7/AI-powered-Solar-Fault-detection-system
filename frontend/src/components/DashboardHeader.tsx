'use client'

import { motion } from 'framer-motion'
import { Sun, Play, Pause, Moon, Lock, Unlock } from 'lucide-react'
import { WeatherData } from '@/lib/types'

export function DashboardHeader({
  isMonitoring,
  setIsMonitoring,
  connectionMode,
  isConnected,
  weather,
  availableStations,
  selectedStation,
  setSelectedStation,
  isFrozen,
  toggleFreeze,
}: {
  isMonitoring: boolean
  setIsMonitoring: (v: boolean) => void
  connectionMode: string
  isConnected: boolean
  weather: WeatherData | null
  availableStations: Set<number>
  selectedStation: number
  setSelectedStation: (id: number) => void
  isFrozen: boolean
  toggleFreeze: () => void
}) {
  return (
    <header className="border-b border-white/10 backdrop-blur-xl bg-dark-900/50 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-6 py-4">
        <div className="flex flex-wrap gap-4 items-center justify-between">
          <div className="flex flex-wrap items-center gap-3">
            <motion.div
              className="w-12 h-12 rounded-xl bg-gradient-to-br from-solar-400 to-amber-500 flex items-center justify-center"
              animate={{ rotate: isMonitoring ? 360 : 0 }}
              transition={{ duration: 10, repeat: Infinity, ease: "linear" }}
            >
              <Sun className="w-7 h-7 text-dark-900" />
            </motion.div>
            <div>
              <h1 className="text-2xl font-bold gradient-text">Solar Panel Monitor</h1>
              <p className="text-sm text-gray-400">Solar Fault Detection System</p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2 px-4 py-2 rounded-full bg-white/5 border border-white/10">
              <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-gray-500'}`} />
              <span className="text-sm">{connectionMode === 'simulator' ? 'Simulator' : connectionMode === 'serial' ? 'USB' : 'WiFi'}</span>
            </div>

            {/* Day/Night indicator in header */}
            {weather?.day_night && (
              <div className={`flex items-center gap-1.5 px-3 py-2 rounded-full text-xs font-medium border ${
                weather.day_night.is_day
                  ? 'bg-yellow-500/10 border-yellow-500/30 text-yellow-300'
                  : 'bg-blue-500/10 border-blue-500/30 text-blue-300'
              }`}>
                {weather.day_night.is_day
                  ? <Sun className="w-3.5 h-3.5" />
                  : <Moon className="w-3.5 h-3.5" />}
                <span>{weather.day_night.period}</span>
                {weather.current && (
                  <span className="text-gray-400 ml-1">{weather.current.temperature?.toFixed(0)}°C</span>
                )}
              </div>
            )}

            {/* Station Selector */}
            {availableStations.size > 0 && (
              <div className="flex bg-white/5 rounded-xl p-1 border border-white/10">
                {Array.from(availableStations).sort().map(id => (
                  <button
                    key={id}
                    onClick={() => setSelectedStation(id)}
                    className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${selectedStation === id
                      ? 'bg-solar-500 text-dark-900 shadow-lg'
                      : 'text-gray-400 hover:text-white'
                      }`}
                  >
                    Station {id}
                  </button>
                ))}
              </div>
            )}

            {/* Freeze button — only shown in simulator mode while monitoring */}
            {isMonitoring && (
              <motion.button
                id="freeze"
                onClick={toggleFreeze}
                className={`px-5 py-3 rounded-xl font-semibold flex items-center gap-2 transition-all border ${isFrozen
                    ? 'bg-blue-500/20 border-blue-400/60 text-blue-300 hover:bg-blue-500/30 shadow-lg shadow-blue-500/20'
                    : 'bg-white/5 border-white/20 text-gray-300 hover:bg-white/10'
                  }`}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                title={isFrozen ? 'Click to resume live updates' : 'Click to freeze current reading for inspection'}
              >
                {isFrozen
                  ? <><Lock className="w-5 h-5" /> Frozen</>
                  : <><Unlock className="w-5 h-5" /> Freeze</>}
              </motion.button>
            )}

            <motion.button
              onClick={() => setIsMonitoring(!isMonitoring)}
              className={`px-6 py-3 rounded-xl font-semibold flex items-center gap-2 transition-all ${isMonitoring
                ? 'bg-red-500/20 border border-red-500/50 text-red-400 hover:bg-red-500/30'
                : 'bg-gradient-to-r from-solar-500 to-amber-500 text-dark-900 hover:shadow-lg hover:shadow-solar-500/30'
                }`}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              {isMonitoring ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5" />}
              {isMonitoring ? 'Stop' : 'Start'} Monitoring
            </motion.button>
          </div>
        </div>
      </div>
    </header>
  )
}
