'use client'

import { useEffect, useRef, useState } from 'react'
import { DashboardHeader } from '@/components/DashboardHeader'
import { FrozenBanner } from '@/components/FrozenBanner'
import { StatusCard } from '@/components/StatusCard'
import { SensorGauges } from '@/components/SensorGauges'
import { SensorHistoryCharts } from '@/components/SensorHistoryCharts'
import { PowerOutputChart } from '@/components/PowerOutputChart'
import { FaultDistributionPanel } from '@/components/FaultDistributionPanel'
import { IntegrationsPanel } from '@/components/IntegrationsPanel'
import { ConnectionPanel } from '@/components/ConnectionPanel'
import { api, stationIds, labels, human, number, Snapshot, ModelReport } from '@/lib/api'
import { HistoryEntry, Prediction, SensorData } from '@/lib/types'

const empty: Snapshot = { stations: [], history: [], forecast: { state: 'warming_up' }, serverTime: 0,
  incidents: [], notifications: [], commands: [], queue: [] }

export default function Home() {
  const [key, setKey] = useState('')
  const [token, setToken] = useState('')
  const [role, setRole] = useState('')
  const [isMonitoring, setIsMonitoring] = useState(false)
  const [connected, setConnected] = useState(false)
  const [selectedStation, setSelectedStation] = useState(1)
  const [snapshot, setSnapshot] = useState<Snapshot>(empty)
  const [frozen, setFrozen] = useState<Snapshot | null>(null)
  const [model, setModel] = useState<ModelReport | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [csvLoading, setCsvLoading] = useState(false)
  const refreshRef = useRef<() => Promise<void>>(async () => {})
  const [readingId, setReadingId] = useState('')
  const [reviewLabel, setReviewLabel] = useState('insufficient_evidence')
  const [reason, setReason] = useState('')
  const stationId = stationIds[selectedStation - 1]
  const view = frozen ?? snapshot
  const station = view.stations.find(s => s.id === stationId)
  const reading = station?.reading
  const result = station?.latest
  const hardware = station?.config.source_mode === 'hardware'
  const operator = role === 'operator'

  async function connect(event: React.FormEvent) {
    event.preventDefault()
    try {
      const candidate = key.trim()
      const me = await api('/me', candidate)
      if (me.role === 'device') throw new Error('Use an operator or viewer key.')
      const report = await api('/model', candidate)
      setToken(candidate); setRole(me.role); setModel(report); setKey('')
      setSnapshot(empty); setFrozen(null); setError(''); setIsMonitoring(true)
    } catch (err) { setError(String(err)) }
  }

  useEffect(() => {
    if (!isMonitoring || !role) return
    let cancelled = false, busy = false, socket: WebSocket | undefined
    let retry: ReturnType<typeof setTimeout> | undefined
    let cursor = 0
    const controller = new AbortController()
    const get = (path: string) => api(path, token, undefined, controller.signal)
    const refresh = async () => {
      if (busy || cancelled) return
      busy = true
      try {
        const [fleet, history, forecast, incidents, commands, reviews] = await Promise.all([
          get('/stations'), get('/stations/' + stationId + '/history?limit=100'),
          get('/stations/' + stationId + '/forecast'), get('/incidents'), get('/commands'), get('/reviews'),
        ])
        if (cancelled) return
        cursor = fleet.cursor
        setSnapshot({ stations: fleet.stations, history: history.readings, forecast, serverTime: fleet.server_time,
          incidents: incidents.incidents, notifications: incidents.notifications, commands, queue: reviews.queue })
      } catch (err) { if (!cancelled) setError(String(err)) }
      finally { busy = false }
    }
    refreshRef.current = refresh
    const open = () => {
      if (cancelled) return
      socket = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws')
      socket.onopen = () => socket?.send(JSON.stringify({ token, cursor }))
      socket.onmessage = event => {
        const message = JSON.parse(event.data)
        if (message.type === 'connected' || message.type === 'changed') { setConnected(true); void refresh() }
      }
      socket.onclose = () => { if (!cancelled) { setConnected(false); retry = setTimeout(open, 2500) } }
      socket.onerror = () => socket?.close()
    }
    void refresh(); open()
    const timer = setInterval(refresh, 2000)
    return () => {
      cancelled = true; controller.abort(); clearInterval(timer); clearTimeout(retry)
      if (socket) { socket.onclose = null; socket.close() }
      setConnected(false)
    }
  }, [token, role, isMonitoring, stationId])

  async function act(path: string, body: unknown, message: string) {
    try {
      await api(path, token, body); setError(''); setNotice(message)
      await refreshRef.current()
    } catch (err) { setError(String(err)) }
  }

  async function downloadCsv() {
    setCsvLoading(true)
    try {
      const response = await api('/stations/' + stationId + '/history?limit=500', token)
      const fields = ['observed_at', 'voltage_v', 'current_a', 'ac_power_w', 'irradiance_wm2',
        'ambient_temp_c', 'surface_temp_c', 'humidity_pct', 'light_adc', 'load_limit_w', 'relay_on', 'dc_power_w', 'light_lux']
      const quote = (value: unknown) => '"' + String(value ?? '').replaceAll('"', '""') + '"'
      const rows = response.readings.map((row: { payload: Record<string, unknown>; result: { stabilized_class?: string } | null }) =>
        [...fields.map(f => quote(row.payload[f])), quote(row.result?.stabilized_class), quote(row.payload.source_kind ?? 'simulated')].join(','))
      const csv = [fields.join(',') + ',prediction,source', ...rows].join('\r\n')
      const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
      const link = document.createElement('a'); link.href = url; link.download = stationId + (hardware ? '-hardware.csv' : '-simulated.csv'); link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
      setNotice('Downloaded ' + rows.length + ' readings for ' + stationId)
    } catch (err) { setError(String(err)) }
    finally { setCsvLoading(false) }
  }

  const sensorData: SensorData | null = reading ? {
    voltage: reading.voltage_v, current: reading.current_a, temperature: reading.ambient_temp_c,
    thermistor_temp: reading.surface_temp_c, humidity: reading.humidity_pct, light_intensity: reading.light_adc,
    irradiance: reading.irradiance_wm2, relay_status: reading.relay_on,
  } : null
  const label = result ? (labels[result.stabilized_class] ?? human(result.stabilized_class)) : ''
  const prediction: Prediction | null = result ? {
    fault_type: label, fault_index: -1, confidence: result.confidence == null ? NaN : result.confidence * 100,
    is_fault: Boolean(labels[result.stabilized_class]) && result.stabilized_class !== 'normal',
    power: (hardware ? reading?.dc_power_w : reading?.ac_power_w) ?? NaN, efficiency: NaN, timestamp: reading?.observed_at ?? '',
    recommendation: result.resolution, decision_state: result.decision_state, probability_method: result.probability_method,
  } : null
  const history: HistoryEntry[] = view.history.filter(row => (row.payload.source_kind ?? 'simulated') === (hardware ? 'hardware' : 'simulated')).map(row => ({
    time: new Date(row.observed_at).toLocaleTimeString(), voltage: row.payload.voltage_v, current: row.payload.current_a,
    temperature: row.payload.ambient_temp_c, light: row.payload.light_adc, humidity: row.payload.humidity_pct,
    thermistor: row.payload.surface_temp_c, power: row.payload.source_kind === 'hardware' ? (row.payload.dc_power_w ?? null) : row.payload.ac_power_w, irradiance: row.payload.irradiance_wm2,
    expected: row.result?.expected_power_w ?? null, efficiency: null, relay: row.payload.relay_on,
    fault: labels[row.result?.stabilized_class ?? ''] ?? human(row.result?.decision_state),
  }))
  const counts: Record<string, number> = {}
  history.forEach(row => { counts[row.fault] = (counts[row.fault] ?? 0) + 1 })
  const command = view.commands.find(c => c.station_id === stationId && c.created_at >= (station?.config.source_changed_at ?? 0))

  return <main className="min-h-screen grid-bg">
    <DashboardHeader isMonitoring={isMonitoring} setIsMonitoring={value => {
      if (!role) { setError('Enter your local access key and connect first.'); return }
      setIsMonitoring(value); setFrozen(null)
    }} connectionMode={hardware ? "wifi" : "simulator"} isConnected={connected} weather={null}
      availableStations={new Set([1, 2, 3])} selectedStation={selectedStation}
      setSelectedStation={id => { setFrozen(null); setSelectedStation(id); setSnapshot(prev => ({ ...prev, history: [], forecast: { state: 'warming_up' } })) }}
      isFrozen={Boolean(frozen)} toggleFreeze={() => setFrozen(frozen ? null : snapshot)} />
    <div className="max-w-7xl mx-auto px-6 py-8">
      <div className="glass-card p-4 mb-6 flex flex-wrap gap-4 items-center justify-between">
        <div><span className="text-xs text-amber-300 border border-amber-500/40 rounded-full px-3 py-1">{hardware ? 'HARDWARE DATA' : 'SIMULATED DATA'}</span>
          <p className="text-sm text-gray-400 mt-2">{station?.name ?? 'East roof'} · <span id="connection">{connected ? 'Live subscription' : 'Not subscribed'}</span>
            {' · '}{station?.online ? 'Station online' : 'Offline / waiting for telemetry'}</p>
          <p className="text-xs text-gray-500 mt-1" id="clock">{view.serverTime ? new Date(view.serverTime * 1000).toLocaleString() : 'Waiting for connection'}</p><p className="text-xs text-gray-500 mt-1">Event: {reading?.observed_at ? new Date(reading.observed_at).toLocaleString() : '—'} · Received: {station?.last_seen ? new Date(station.last_seen * 1000).toLocaleString() : '—'}</p></div>
        <form id="login" onSubmit={connect} className="flex flex-wrap gap-2 items-end">
          <label className="text-xs text-gray-400">Local access key<input id="token" type="password" value={key}
            autoComplete="off" onChange={e => setKey(e.target.value)} className="block mt-1 input" placeholder="Paste operator or viewer key" /></label>
          <button className="solar-button">Connect</button>
          <span className="text-xs text-gray-400 w-full">{role ? 'Connected as ' + role + ' · key kept in page memory' : 'Run python -m solarsense credentials'}</span>
        </form>
      </div>
      {error && <div role="alert" className="mb-4 p-4 bg-red-500/10 border border-red-500/40 rounded-xl break-words">{error}</div>}
      {notice && <p role="status" className="text-sm text-solar-300 mb-4">{notice}</p>}
      <FrozenBanner isFrozen={Boolean(frozen)} toggleFreeze={() => setFrozen(null)} />
      {!isMonitoring && role && <p className="mb-4 text-amber-300">Display monitoring stopped. The independent simulator and backend continue running.</p>}
      {station && !station.online && <p className="mb-4 text-amber-300">Last known values only. {hardware ? "Check the gateway or serial bridge for fresh readings." : "Start the simulator to receive fresh readings."}</p>}
      <div className="mb-8"><StatusCard prediction={prediction} /></div>
      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-12 lg:col-span-8 min-w-0">
          <SensorGauges sensorData={sensorData} connectionMode={hardware ? "wifi" : "simulator"} prediction={prediction} />
          <SensorHistoryCharts history={history} />
          <PowerOutputChart history={history} hardware={hardware} />
          <section className="glass-card p-6 mt-6"><h3 className="text-lg font-semibold mb-3">Power forecast</h3>
            {view.forecast.state === 'available' ? <div className="flex flex-wrap gap-6">{Object.entries(view.forecast.horizons_minutes ?? {}).map(([h, value]) =>
              <div key={h}><p className="text-gray-400">{h} minutes</p><strong>{number(value.power_w)} W</strong><p className="text-xs text-gray-500">{value.method}</p></div>)}</div>
              : <p className="text-gray-400">{human(view.forecast.state)} · {view.forecast.reason ?? 'Collecting distinct five-minute intervals.'}</p>}
          </section>
          <section className="glass-card p-6 mt-6"><h3 className="text-lg font-semibold mb-3">Fault diagnosis and resolution</h3>
            <p>{result?.resolution ?? 'Waiting for committed inference.'}</p>
            <p className="text-sm text-gray-400 mt-2">Input quality: {human(result?.quality_state)} · Decision: {human(result?.decision_state)}</p>
            <p className="text-sm text-gray-400 mt-2">Raw model class: {human(result?.raw_class)} · Sustained power deficit: {result?.sustained_deficit ? 'Yes' : 'No'}</p>
            <div className="mt-4 text-sm">{result?.explanation?.map(item => <p className="flex justify-between gap-4" key={item.feature}>
              <span>{human(item.feature)} = {number(item.value, 3)}</span><span>{number(item.contribution, 3)}</span></p>)}</div>
            <p className="text-xs text-gray-500 mt-3">SHAP contributions describe the underlying forest prediction, not a proven physical cause.</p>
          </section>
          <section className="glass-card p-6 mt-6"><h3 className="text-lg font-semibold mb-3">Incident history</h3>
            {!view.incidents.length && <p className="text-gray-400">No incidents recorded.</p>}
            {view.incidents.slice(0, 12).map(item => <div key={item.id} className="border-b border-white/10 py-3 flex flex-wrap justify-between gap-3">
              <div><p>{human(item.label)} · {item.station_id}</p><p className="text-xs text-gray-400">#{item.id} · {item.status} · {new Date(item.opened_at * 1000).toLocaleString()}</p></div>
              <button className="small-button" disabled={!operator || Boolean(item.acknowledged_at)} onClick={() => act('/incidents/' + item.id + '/ack', {}, 'Incident acknowledged.')}>{item.acknowledged_at ? 'Acknowledged' : 'Acknowledge'}</button>
            </div>)}
          </section>
        </div>
        <div className="col-span-12 lg:col-span-4 space-y-6 min-w-0">
          <section className="glass-card p-6"><h3 className="text-lg font-semibold mb-3">Sensor environment</h3>
            <p className="text-xs text-amber-300 mb-3">{hardware ? 'Hardware sensor readings · missing channels stay unavailable' : 'Simulated station conditions'}</p>
            <div className="grid grid-cols-2 gap-4"><div><p className="text-gray-400 text-sm">Air temperature</p><strong>{number(reading?.ambient_temp_c)} °C</strong></div>
              <div><p className="text-gray-400 text-sm">Humidity</p><strong>{number(reading?.humidity_pct)} %</strong></div>
              <div><p className="text-gray-400 text-sm">Irradiance</p><strong>{number(reading?.irradiance_wm2)} W/m²</strong></div>
              <div><p className="text-gray-400 text-sm">Load limit</p><strong>{number(reading?.load_limit_w)} W</strong></div></div>
          </section>
          <IntegrationsPanel token={token} role={role} stationId={stationId} onSource={async () => { setFrozen(null); await refreshRef.current() }} />
          {!hardware && <ConnectionPanel disabled={!operator} stationId={stationId} onApply={body => act('/stations/' + stationId + '/scenario', body, 'Condition requested. Waiting for the simulator to apply it.')} />}
          <section className="glass-card p-6"><h3 className="text-lg font-semibold mb-3">Relay Control (Station {selectedStation})</h3>
            <div className="p-4 rounded-xl bg-white/5 border border-white/10 text-center"><p className="text-xs text-gray-400">{hardware ? 'Reported hardware relay activation' : 'Confirmed virtual relay'}</p>
              <p className="text-3xl font-bold text-solar-400 mt-2">{reading && (!hardware || reading.hardware_protocol === 'espnow_gateway') ? (reading.relay_on ? 'ON' : 'OFF') : '—'}</p></div>
            <div className="grid grid-cols-2 gap-2 mt-4">{[true, false].map(on => <button key={String(on)} id={on ? 'relay-on' : 'relay-off'} className="small-button" disabled={!operator}
              onClick={() => act('/stations/' + stationId + '/commands', { relay_on: on, ttl_seconds: 30 }, hardware ? 'Command queued; confirmation requires fresh gateway feedback.' : 'Relay command queued; confirmation requires the simulator.')}>{hardware ? (on ? 'Activate' : 'Deactivate') : 'Turn ' + (on ? 'On' : 'Off')}</button>)}</div>
            <p id="command-status" className="text-xs text-gray-400 mt-3">{command ? '#' + command.id + ': requested ' + (command.desired ? 'ON' : 'OFF') + ' · ' + command.status + (command.confirmed === null ? '' : ' · confirmed ' + (command.confirmed ? 'ON' : 'OFF')) : 'No relay commands yet.'}</p>
          </section>
          <FaultDistributionPanel faultCounts={counts} />
          <section className="glass-card p-6"><h3 className="text-lg font-semibold mb-3">System Info</h3>
            <p id="model-version" className="text-sm break-all">{hardware ? 'Hardware release ' + (result?.model_version ?? 'waiting for readings') : model ? 'Release ' + model.model_version : 'Connect to load model evidence'}</p>
            {hardware && <p className="text-xs text-amber-300 mt-3">Original six-sensor, five-class hardware model. The benchmark below belongs to the separate synthetic model and is not a hardware accuracy claim.</p>}
            {model && <div className="text-sm space-y-2 mt-3"><p>Held-out accuracy: {number(model.classification.accuracy * 100, 2)}%</p><p>Macro F1: {number(model.classification.macro_f1, 4)}</p>
              <p>Accepted coverage: {number(model.coverage * 100)}%</p><p>{model.dataset.rows} synthetic rows · whole-session splits</p>
              <p className="text-xs text-gray-400">{Object.entries(model.baselines).map(([name, value]) => human(name) + ' F1 ' + number(value.test.macro_f1, 4)).join(' · ')}</p></div>}
            <p className="text-xs text-gray-400 mt-3">Displayed readings: {history.length} · refresh: 2 seconds</p>
          </section>
          <section className="glass-card p-6"><h3 className="text-lg font-semibold mb-3">Notifications</h3>
            <p className="text-xs text-gray-400">Local incident outbox. External technician delivery is tracked separately above.</p>
            {view.notifications.slice(0, 5).map(item => <p key={item.event_id} className="text-sm mt-2">#{item.event_id} · {human(item.payload.kind)} · {item.status} ({item.attempts} attempts)</p>)}
            {!view.notifications.length && <p className="text-sm text-gray-400 mt-2">No notifications yet.</p>}
          </section>
          <section className="glass-card p-6"><h3 className="text-lg font-semibold mb-3">Download CSV Data</h3>
            <p className="text-sm text-gray-400 mb-3">{station?.name ?? stationId} · latest 500 stored readings · source recorded in CSV</p>
            <button className="small-button w-full" disabled={!role || csvLoading} onClick={downloadCsv}>{csvLoading ? 'Downloading…' : 'Download CSV'}</button>
          </section>
          <section className="glass-card p-6"><h3 className="text-lg font-semibold mb-3">Human review</h3>
            <div className="space-y-2 mb-3">{view.queue.slice(0, 4).map(item => <button className="small-button text-xs" key={item.telemetry_id} onClick={() => setReadingId(String(item.telemetry_id))}>#{item.telemetry_id} · {human(item.result.decision_state)}</button>)}</div>
            <form className="space-y-3" onSubmit={event => { event.preventDefault(); void act('/readings/' + readingId + '/reviews', { label: reviewLabel, reason }, 'Review saved. No automatic retraining.') }}>
              <label className="block text-sm">Reading ID<input className="input w-full" type="number" min="1" required value={readingId} onChange={e => setReadingId(e.target.value)} /></label>
              <label className="block text-sm">Independent label<select className="input w-full" value={reviewLabel} onChange={e => setReviewLabel(e.target.value)}>{['insufficient_evidence', 'unknown', ...Object.keys(labels)].map(label => <option key={label}>{label}</option>)}</select></label>
              <label className="block text-sm">Evidence<input className="input w-full" required minLength={5} maxLength={500} value={reason} onChange={e => setReason(e.target.value)} /></label>
              <button className="small-button" disabled={!operator}>Save review</button>
            </form>
          </section>
        </div>
      </div>
    </div>
    <footer className="border-t border-white/10 mt-12 py-6 text-center text-gray-500 text-sm px-6">
      <p>Solar Panel Fault Detection System · Powered by Machine Learning</p>
      <p className="mt-2">Simulation and hardware sources are explicitly labelled. Physical relay commands require server enablement. <a className="text-solar-400 underline" href="/operations/">Operations dashboard</a></p>
    </footer>
  </main>
}
