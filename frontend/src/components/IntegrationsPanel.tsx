'use client'

import { useEffect, useState } from 'react'
import { Radio, CloudSun, Bell } from 'lucide-react'
import { api, number, human } from '@/lib/api'

type Contact = { name: string; phone: string; channel: string; enabled: boolean; allow_simulated: boolean }
type Alert = { id: number; station_id: string; status: string; error: string | null; payload: { message: string; contact: { phone: string } } }
type Settings = { source_modes: Record<string, string>; notification_mode: string; physical_relays_enabled: boolean; gateway_configured: boolean; channels_ready: Record<string, boolean> }
type Weather = { available: boolean; stale: boolean; location?: string; fetched_at?: number; error?: string; current?: { temperature_2m: number; relative_humidity_2m: number; cloud_cover: number; precipitation: number; is_day: number } }
const emptyContact: Contact = { name: '', phone: '', channel: 'whatsapp', enabled: false, allow_simulated: false }

export function IntegrationsPanel({ token, role, stationId, onSource }: {
  token: string; role: string; stationId: string; onSource: () => Promise<void>
}) {
  const [settings, setSettings] = useState<Settings | null>(null)
  const [weather, setWeather] = useState<Weather | null>(null)
  const [contact, setContact] = useState<Contact>(emptyContact)
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [status, setStatus] = useState('')
  const [preview, setPreview] = useState('')
  const operator = role === 'operator'
  useEffect(() => {
    if (!role) return
    let cancelled = false
    setContact(emptyContact); setPreview(''); setStatus('')
    const update = async () => {
      try {
        const [config, jobs] = await Promise.all([api('/integrations', token), api('/technician-alerts', token)])
        if (!cancelled) { setSettings(config); setAlerts(jobs.alerts) }
      } catch (err) { if (!cancelled) setStatus(String(err)) }
    }
    void update()
    api('/weather', token).then(value => { if (!cancelled) setWeather(value) }).catch(() => { if (!cancelled) setWeather({ available: false, stale: true }) })
    if (operator) api('/stations/' + stationId + '/technician', token).then(value => {
      if (!cancelled) setContact(value.contact ?? emptyContact)
    }).catch(err => { if (!cancelled) setStatus(String(err)) })
    const timer = setInterval(update, 5000)
    return () => { cancelled = true; clearInterval(timer) }
  }, [token, role, stationId, operator])
  async function source(mode: string) {
    try {
      await api('/stations/' + stationId + '/source', token, { mode })
      setSettings(await api('/integrations', token)); setStatus('Station source changed to ' + mode)
      await onSource()
    } catch (err) { setStatus(String(err)) }
  }
  return <>
    <section className="glass-card p-6">
      <h3 className="text-lg font-semibold mb-3 flex gap-2 items-center"><Radio className="w-5 h-5 text-solar-400" />Hardware connection</h3>
      <div className="grid grid-cols-2 gap-2">{['simulated', 'hardware'].map(mode => <button key={mode}
        data-testid={'source-' + mode} disabled={!operator} onClick={() => source(mode)}
        className={'small-button ' + (settings?.source_modes[stationId] === mode ? 'border-solar-500 text-solar-300' : '')}>{mode === 'simulated' ? 'Simulator' : 'ESP32 / Serial'}</button>)}</div>
      <p className="text-xs text-gray-400 mt-3">Gateway: {settings?.gateway_configured ? 'configured' : 'not configured'}. Physical relay commands: {settings?.physical_relays_enabled ? 'enabled' : 'disabled'}.</p>
      <p className="text-xs text-gray-500 mt-2">The original ESP-NOW gateway posts to /api/gateway-data. Serial devices use the separate serial bridge. Hardware mode never substitutes simulated readings.</p>
    </section>
    <section className="glass-card p-6">
      <h3 className="text-lg font-semibold mb-3 flex gap-2 items-center"><CloudSun className="w-5 h-5 text-solar-400" />Live weather</h3>
      {weather?.available && weather.current ? <>
        <p className="text-sm text-gray-300">{weather.location} · {weather.current.is_day ? 'Day' : 'Night'} {weather.stale ? '· cached / stale' : ''}</p>
        <div className="grid grid-cols-2 gap-3 mt-3"><p>{number(weather.current.temperature_2m)} °C</p><p>{number(weather.current.relative_humidity_2m)}% humidity</p>
          <p>{number(weather.current.cloud_cover)}% cloud</p><p>{number(weather.current.precipitation)} mm rain</p></div>
        <p className="text-xs text-gray-400 mt-3">{weather.current.cloud_cover > 70 ? 'Heavy cloud may reduce generation. It does not establish the cause of a fault.' : 'Weather context does not replace inspection of the sensors and electrical circuit.'}</p>
      </> : <p className="text-sm text-gray-400">{weather ? 'Weather unavailable. Sensor monitoring continues.' : 'Connect to load local weather.'}</p>}
      <p className="text-xs text-gray-500 mt-3">Weather data: <a className="underline" href="https://open-meteo.com/" target="_blank" rel="noreferrer">Open-Meteo</a>. Local conditions; separate from simulated sensor values.</p>
      <button className="small-button mt-3" disabled={!role} onClick={async () => { try { setWeather(await api('/weather', token)) } catch { setWeather({ available: false, stale: true }) } }}>Refresh weather</button>
    </section>
    <section className="glass-card p-6">
      <h3 className="text-lg font-semibold mb-3 flex gap-2 items-center"><Bell className="w-5 h-5 text-solar-400" />Technician alerts</h3>
      <p className="text-xs text-amber-300 mb-3">{settings?.notification_mode === 'live' ? 'Live delivery enabled on server' : 'Preview mode — no messages leave this app'}</p>
      {operator ? <form className="space-y-3" onSubmit={async event => {
        event.preventDefault()
        try { const value = await api('/stations/' + stationId + '/technician', token, contact); setStatus('Technician saved. ' + value.note) }
        catch (err) { setStatus(String(err)) }
      }}>
        <label className="block text-sm">Technician name<input className="input w-full" required maxLength={80} value={contact.name} onChange={e => setContact({ ...contact, name: e.target.value })} /></label>
        <label className="block text-sm">Technician phone<input className="input w-full" type="tel" required pattern="\+[1-9][0-9]{7,14}" placeholder="International format, e.g. +977…" value={contact.phone} onChange={e => setContact({ ...contact, phone: e.target.value })} /></label>
        <label className="block text-sm">Alert channel<select className="input w-full" value={contact.channel} onChange={e => setContact({ ...contact, channel: e.target.value })}><option value="whatsapp">WhatsApp</option><option value="sms">SMS</option></select></label>
        <label className="flex gap-2 text-sm"><input type="checkbox" checked={contact.enabled} onChange={e => setContact({ ...contact, enabled: e.target.checked })} />Enable automatic alerts</label>
        <label className="flex gap-2 text-sm"><input type="checkbox" checked={contact.allow_simulated} onChange={e => setContact({ ...contact, allow_simulated: e.target.checked })} />Include simulated incidents</label>
        <button className="solar-button w-full">Save technician</button>
        <button type="button" className="small-button w-full" onClick={async () => {
          try { setPreview((await api('/stations/' + stationId + '/alert-preview', token)).message) } catch (err) { setStatus(String(err)) }
        }}>Preview message</button>
      </form> : <p className="text-sm text-gray-400">Operator access is required to configure the technician.</p>}
      {status && <p data-testid="integration-status" className="text-sm text-solar-300 mt-3 break-words">{status}</p>}
      {preview && <pre data-testid="alert-preview" className="mt-3 text-xs whitespace-pre-wrap bg-white/5 p-3 rounded-lg">{preview}</pre>}
      <p className="text-xs text-gray-500 mt-3">Alerts are created on fault and recovery transitions, not every reading. Submitted means the provider accepted the message; delivered requires provider confirmation.</p>
      <div className="space-y-3 mt-4">{alerts.filter(a => a.station_id === stationId).slice(0, 5).map(alert => <div key={alert.id} className="p-3 bg-white/5 rounded-lg text-xs">
        <p className="text-solar-300">#{alert.id} · {human(alert.status)} · {alert.payload.contact.phone}</p>
        <p className="whitespace-pre-wrap mt-2">{alert.payload.message}</p>{alert.error && <p className="text-red-300 mt-2">{alert.error}</p>}
      </div>)}</div>
    </section>
  </>
}
