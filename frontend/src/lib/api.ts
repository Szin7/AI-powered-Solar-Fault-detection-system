export async function api(path: string, token: string, body?: unknown, signal?: AbortSignal) {
  const response = await fetch('/api/v1' + path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: {
      ...(token ? { Authorization: 'Bearer ' + token } : {}),
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
    },
    body: body === undefined ? undefined : JSON.stringify(body), signal,
  })
  const value = await response.json()
  if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : JSON.stringify(value.detail))
  return value
}

export const stationIds = ['roof-east', 'roof-west', 'lab-panel']
export const labels: Record<string, string> = {
  normal: 'Normal', open_circuit: 'Open_Circuit', short_circuit: 'Short_Circuit',
  partial_shading: 'Partial_Shading', soiling: 'Dust_Accumulation', inverter_fault: 'Inverter_Fault',
}
export const human = (value: unknown) => String(value ?? 'unavailable').replaceAll('_', ' ')
export const number = (value: unknown, digits = 1) => typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '—'

export interface Reading {
  source_kind?: string; dc_power_w?: number | null; light_lux?: number | null; hardware_protocol?: string
  voltage_v: number | null; current_a: number | null; ac_power_w: number | null
  irradiance_wm2: number | null; ambient_temp_c: number | null; surface_temp_c: number | null
  humidity_pct: number | null; light_adc: number | null; relay_on: boolean
  load_limit_w: number | null; observed_at: string
}
export interface Result {
  raw_class: string; stabilized_class: string; decision_state: string; confidence: number | null
  probability_method: string; quality_state: string; resolution: string; model_version: string
  expected_power_w: number | null; sustained_deficit: boolean
  explanation: { feature: string; value: number; contribution: number }[]
}
export interface Station {
  config: { source_mode?: string; source_changed_at?: number }; id: string; name: string; online: boolean; last_seen: number | null; latest_id: number | null
  reading: Reading | null; latest: Result | null
}
export interface HistoryRow { id: number; payload: Reading; result: Result | null; observed_at: string }
export interface Forecast {
  state: string; reason?: string
  horizons_minutes?: Record<string, { power_w: number; method: string }>
}
export interface Incident { id: number; station_id: string; label: string; status: string; opened_at: number; acknowledged_at: number | null }
export interface Notification { event_id: number; status: string; attempts: number; payload: { kind: string } }
export interface Command { created_at: number; id: string; station_id: string; desired: boolean; confirmed: boolean | null; status: string }
export interface ModelReport {
  model_version: string; classification: { accuracy: number; macro_f1: number }; coverage: number
  baselines: Record<string, { test: { macro_f1: number } }>; dataset: { rows: number }; seed: number
}
export interface Snapshot {
  stations: Station[]; history: HistoryRow[]; forecast: Forecast; serverTime: number
  incidents: Incident[]; notifications: Notification[]; commands: Command[]
  queue: { telemetry_id: number; station_id: string; result: Result }[]
}
