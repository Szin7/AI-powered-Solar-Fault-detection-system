'use client'

import { useEffect, useState } from 'react'
import { Settings, RefreshCw, Usb, Wifi } from 'lucide-react'
import { human } from '@/lib/api'

const fields = [
  ['voltage_v', 'Voltage', 'V', 0, 80, 0.1], ['current_a', 'Current', 'A', 0, 30, 0.01],
  ['ambient_temp_c', 'Air temperature', '°C', -30, 70, 0.5], ['surface_temp_c', 'Panel temperature', '°C', -30, 120, 0.5],
  ['humidity_pct', 'Humidity', '%', 0, 100, 0.5], ['light_adc', 'Light intensity', 'ADC', 0, 4095, 1],
  ['irradiance_wm2', 'Irradiance', 'W/m²', 0, 1500, 1], ['ac_power_w', 'AC output', 'W', 0, 4000, 1],
] as const
const defaults: Record<string, number> = { voltage_v: 35, current_a: 7, ambient_temp_c: 25, surface_temp_c: 42,
  humidity_pct: 50, light_adc: 3200, irradiance_wm2: 800, ac_power_w: 230 }

export function ConnectionPanel({ disabled, stationId, onApply }: {
  disabled: boolean; stationId: string; onApply: (body: unknown) => Promise<void>
}) {
  const [tab, setTab] = useState('preset')
  const [fault, setFault] = useState('normal')
  const [severity, setSeverity] = useState(0.7)
  const [network, setNetwork] = useState('normal')
  const [values, setValues] = useState(defaults)
  useEffect(() => { setTab('preset'); setFault('normal'); setNetwork('normal') }, [stationId])
  return <div className="glass-card p-6">
    <h3 className="text-lg font-semibold mb-4 flex items-center gap-2"><Settings className="w-5 h-5 text-solar-400" />Connection Mode</h3>
    <div className="grid grid-cols-3 gap-2 mb-3">
      <div className="p-3 rounded-xl border border-solar-500 bg-white/10 text-center"><RefreshCw className="w-6 h-6 mx-auto mb-2 text-blue-400" /><span className="text-xs">Simulator</span></div>
      <button disabled title="Hardware adapter is not connected" className="p-3 rounded-xl border border-white/10 text-center opacity-40"><Usb className="w-6 h-6 mx-auto mb-2" /><span className="text-xs">USB/Serial</span></button>
      <button disabled title="Hardware adapter is not connected" className="p-3 rounded-xl border border-white/10 text-center opacity-40"><Wifi className="w-6 h-6 mx-auto mb-2" /><span className="text-xs">WiFi/ESP32</span></button>
    </div>
    <p className="text-xs text-gray-400 mb-4">Virtual devices only. USB and ESP32 adapters are not connected.</p>
    <div className="flex bg-white/5 rounded-lg p-1 border border-white/10 mb-4">{['preset', 'manual'].map(value =>
      <button key={value} onClick={() => setTab(value)} className={'flex-1 py-1.5 rounded-md text-sm capitalize ' + (tab === value ? 'bg-solar-500 text-dark-900' : 'text-gray-400')}>{value}</button>)}</div>
    <form onSubmit={event => { event.preventDefault(); void onApply({ fault: tab === 'manual' ? 'normal' : fault,
      severity, network, cloud: 1, enabled: true, manual: tab === 'manual' ? values : null }) }}>
      {tab === 'preset' ? <><h4 className="text-sm text-gray-400 mb-3">Simulate Fault Type</h4>
        <div className="grid grid-cols-2 gap-2">{['normal', 'open_circuit', 'partial_shading', 'short_circuit', 'soiling', 'inverter_fault', 'sensor_stuck', 'sensor_offset', 'missing', 'unknown'].map(value =>
          <button type="button" key={value} onClick={() => setFault(value)} className={'p-3 rounded-lg border text-sm text-left ' + (fault === value ? 'border-solar-500 bg-white/10' : 'border-white/10')}>
            {value === 'soiling' ? 'Dust / soiling' : human(value)}</button>)}</div>
        <label className="block text-sm text-gray-400 mt-4">Severity<input className="input w-full" type="number" min="0" max="1" step="0.05" value={severity} onChange={e => setSeverity(Number(e.target.value))} /></label>
      </> : <div className="space-y-2">{fields.map(([key, label, unit, min, max, step]) => <label key={key} className="flex items-center gap-2 text-xs text-gray-400">
        <span className="w-28 shrink-0">{label}</span><input aria-label={label} className="input min-w-0 w-full text-right" type="number" required min={min} max={max} step={step}
          value={values[key]} onChange={e => setValues({ ...values, [key]: Number(e.target.value) })} /><span className="w-9 shrink-0">{unit}</span></label>)}
        <p className="text-xs text-gray-500">Manual readings are sent by the simulator. Repeated fixed values may trigger stuck-sensor detection.</p></div>}
      <label className="block text-sm text-gray-400 mt-4">Telemetry link<select className="input w-full" value={network} onChange={e => setNetwork(e.target.value)}>
        {['normal', 'disconnect', 'delay', 'duplicate'].map(value => <option key={value}>{value}</option>)}</select></label>
      <button id="apply" disabled={disabled} className="solar-button w-full mt-4">{tab === 'manual' ? 'Apply Values' : 'Apply condition'}</button>
    </form>
    <button className="small-button w-full mt-2" disabled={disabled} onClick={() => onApply({ enabled: false })}>Resume scheduled scenario</button>
    <p className="text-xs text-gray-500 mt-3">Operator access required. Changes apply to the selected station.</p>
  </div>
}
