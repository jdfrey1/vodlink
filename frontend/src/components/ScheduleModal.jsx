import { useState, useEffect } from 'react'

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const HOURS = Array.from({ length: 24 }, (_, i) => {
  const ampm = i < 12 ? 'AM' : 'PM'
  const h = i % 12 || 12
  return { value: i, label: `${h}:00 ${ampm}` }
})

const SELECT = 'bg-raised text-sm text-secondary rounded-lg px-3 py-1.5 border border-border focus:outline-none focus:border-blue-500'

export default function ScheduleModal({ onClose }) {
  const [cfg, setCfg] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    fetch('/api/schedule').then((r) => r.json()).then(setCfg).catch(() => {})
  }, [])

  const set = (patch) => setCfg((c) => ({ ...c, ...patch }))

  const handleSave = async () => {
    setSaving(true)
    setSaved(false)
    try {
      const res = await fetch('/api/schedule', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cfg),
      })
      if (res.ok) { const updated = await res.json(); setCfg(updated); setSaved(true); setTimeout(() => setSaved(false), 2000) }
    } finally { setSaving(false) }
  }

  const fmtNext = (iso) => iso ? new Date(iso).toLocaleString() : null

  const Toggle = ({ value, onChange, label }) => (
    <label className="flex items-center gap-3 cursor-pointer">
      <div onClick={onChange} className={`relative w-10 h-5 rounded-full transition-colors ${value ? 'bg-blue-600' : 'bg-elevated'}`}>
        <span className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${value ? 'translate-x-5' : 'translate-x-0.5'}`} />
      </div>
      <span className="text-sm font-medium text-fg">{label}</span>
    </label>
  )

  const Pills = ({ options, value, onChange }) => (
    <div className="flex gap-2">
      {options.map(([val, label]) => (
        <button key={val} onClick={() => onChange(val)}
          className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${value === val ? 'bg-blue-600 text-white' : 'bg-raised text-muted hover:text-fg'}`}>
          {label}
        </button>
      ))}
    </div>
  )

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-surface border border-border rounded-xl shadow-2xl w-full max-w-md mx-4">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <h2 className="text-base font-semibold text-fg">Schedule Scans</h2>
          <button onClick={onClose} className="text-subtle hover:text-fg text-lg leading-none">✕</button>
        </div>

        {!cfg ? (
          <div className="px-5 py-8 text-center text-subtle text-sm">Loading…</div>
        ) : (
          <div className="px-5 py-4 space-y-4">
            <Toggle value={cfg.enabled} onChange={() => set({ enabled: !cfg.enabled })}
              label={cfg.enabled ? 'Scheduled scans enabled' : 'Scheduled scans disabled'} />

            <div className={cfg.enabled ? '' : 'opacity-40 pointer-events-none'}>
              <div className="mb-4">
                <p className="text-xs text-subtle uppercase tracking-wider mb-2">Scan Type</p>
                <Pills options={[['all','All'],['movie','Movies'],['series','Series']]} value={cfg.scan_type} onChange={(v) => set({ scan_type: v })} />
              </div>

              <label className="flex items-center gap-2 mb-4 cursor-pointer">
                <input type="checkbox" checked={cfg.full} onChange={(e) => set({ full: e.target.checked })} className="accent-blue-600 w-4 h-4" />
                <span className="text-sm text-secondary">Full rescan (re-parse all NFOs)</span>
              </label>

              <div className="mb-4">
                <p className="text-xs text-subtle uppercase tracking-wider mb-2">Frequency</p>
                <Pills options={[['daily','Daily'],['weekly','Weekly'],['monthly','Monthly']]} value={cfg.frequency} onChange={(v) => set({ frequency: v })} />
              </div>

              {cfg.frequency === 'weekly' && (
                <div className="mb-4">
                  <p className="text-xs text-subtle uppercase tracking-wider mb-2">Day of Week</p>
                  <select value={cfg.day_of_week} onChange={(e) => set({ day_of_week: Number(e.target.value) })} className={SELECT}>
                    {DAYS.map((d, i) => <option key={i} value={i}>{d}</option>)}
                  </select>
                </div>
              )}

              {cfg.frequency === 'monthly' && (
                <div className="mb-4">
                  <p className="text-xs text-subtle uppercase tracking-wider mb-2">Day of Month</p>
                  <select value={cfg.day_of_month} onChange={(e) => set({ day_of_month: Number(e.target.value) })} className={SELECT}>
                    {Array.from({ length: 28 }, (_, i) => i + 1).map((d) => <option key={d} value={d}>{d}</option>)}
                  </select>
                </div>
              )}

              <div className="mb-2">
                <p className="text-xs text-subtle uppercase tracking-wider mb-2">Time of Day</p>
                <select value={cfg.hour} onChange={(e) => set({ hour: Number(e.target.value) })} className={SELECT}>
                  {HOURS.map(({ value, label }) => <option key={value} value={value}>{label}</option>)}
                </select>
              </div>

              {cfg.next_run && (
                <p className="text-xs text-subtle mt-3">Next run: {fmtNext(cfg.next_run)}</p>
              )}
            </div>
          </div>
        )}

        <div className="px-5 py-4 border-t border-border flex items-center justify-end gap-3">
          {saved && <span className="text-xs text-green-600 dark:text-green-400">Saved</span>}
          <button onClick={onClose} className="px-4 py-2 bg-raised hover:bg-elevated text-fg text-sm rounded-lg transition-colors">Close</button>
          <button onClick={handleSave} disabled={saving || !cfg}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm rounded-lg font-medium transition-colors">
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}
