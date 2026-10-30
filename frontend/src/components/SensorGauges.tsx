'use client'

import { motion } from 'framer-motion'
import { Sun, Thermometer, Zap, Activity, Eye, Percent, AlertTriangle } from 'lucide-react'
import { Gauge } from '@/components/Gauge'
import { isCurrentAbnormal } from '@/lib/constants'
import { SensorData, Prediction } from '@/lib/types'

export function SensorGauges({ sensorData, connectionMode, prediction }: {
  sensorData: SensorData | null
  connectionMode: string
  prediction: Prediction | null
}) {
  return (
    <>
      {/* Environmental Sensor Gauges */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
        <Gauge
          value={sensorData?.humidity ?? null}
          min={0} max={100}
          label="Humidity"
          unit="%"
          color="#06b6d4"
          icon={Sun}
        />
        <Gauge
          value={sensorData?.temperature ?? null}
          min={0} max={100}
          label="Air Temperature"
          unit="°C"
          color="#f59e0b"
          icon={Thermometer}
        />
        <Gauge
          value={sensorData?.thermistor_temp ?? null}
          min={0} max={100}
          label="Panel Temp"
          unit="°C"
          color="#ec4899"
          icon={Thermometer}
        />
      </div>

      {/* Electrical & Solar Gauges */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <Gauge
          value={sensorData?.voltage ?? null}
          min={0} max={connectionMode === "wifi" ? 25 : 80}
          label="Voltage"
          unit="V"
          color="#3b82f6"
          icon={Zap}
        />
        <Gauge
          value={sensorData?.current ?? null}
          min={0} max={connectionMode === "wifi" ? 2 : 30}
          label="Current"
          unit="A"
          color="#ef4444"
          icon={Activity}
        />
        <Gauge
          value={sensorData?.light_intensity ?? null}
          min={0} max={4095}
          label="Light (ADC)"
          unit="ADC"
          color="#22c55e"
          icon={Eye}
        />
        <Gauge
          value={sensorData?.irradiance ?? null}
          min={0} max={1500}
          label="Irradiance"
          unit="W/m²"
          color="#8b5cf6"
          icon={Sun}
        />
      </div>

    </>
  )
}
