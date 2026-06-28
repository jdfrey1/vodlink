import { useState, useEffect, useRef } from 'react'

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const HOURS = Array.from({ length: 24 }, (_, i) => {
  const ampm = i < 12 ? 'AM' : 'PM'
  const h = i % 12 || 12
  return { value: i, label: `${h}:00 ${ampm}` }
})

const SELECT = 'bg-bg text-sm text-secondary rounded px-2 py-1 border border-border focus:outline-none focus:border-blue-500'

function fmt(ts) { return ts ? new Date(ts * 1000).toLocaleString() : '—' }
function fmtSize(b) {
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / (1024 * 1024)).toFixed(1)} MB`
}

const SCHED_DEFAULTS = { keep_n: 7, schedule_enabled: false, schedule_frequency: 'daily', schedule_hour: 2, schedule_day_of_week: 0, schedule_day_of_month: 1 }

export default function BackupModal({ onClose }) {
  const [backups, setBackups] = useState([])
  const [sched, setSched] = useState(SCHED_DEFAULTS)
  const [creating, setCreating] = useState(false)
  const [restoring, setRestoring] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [savingSettings, setSavingSettings] = useState(false)
  const [msg, setMsg] = useState(null)
  const fileRef = useRef()

  const loadBackups = () => fetch('/api/backups').then((r) => r.json()).then(setBackups).catch(() => {})
  const loadSettings = () => fetch('/api/backup/settings').then((r) => r.json()).then((s) => setSched((p) => ({ ...p, ...s }))).catch(() => {})
  useEffect(() => { loadBackups(); loadSettings() }, [])

  const set = (patch) => setSched((s) => ({ ...s, ...patch }))
  const flash = (text, ok = true) => { setMsg({ text, ok }); setTimeout(() => setMsg(null), 3000) }

  const handleCreate = async () => {
    setCreating(true)
    try {
      const res = await fetch('/api/backups', { method: 'POST' })
      if (res.ok) { flash('Backup created'); loadBackups() } else flash('Backup failed', false)
    } finally { setCreating(false) }
  }

  const handleSaveSettings = async () => {
    setSavingSettings(true)
    try {
      const res = await fetch('/api/backup/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(sched) })
      if (res.ok) { const updated = await res.json(); setSched((s) => ({ ...s, ...updated })); flash('Settings saved') }
      else flash('Save failed', false)
    } finally { setSavingSettings(false) }
  }

  const handleDownload = (filename) => { const a = document.createElement('a'); a.href = `/api/backups/${encodeURIComponent(filename)}`; a.download = filename; a.click() }

  const handleRestore = async (filename) => {
    if (!confirm(`Restore from "${filename}"? Current database will be replaced.`)) return
    setRestoring(filename)
    try {
      const res = await fetch(`/api/backups/${encodeURIComponent(filename)}/restore`, { method: 'POST' })
      if (res.ok) { flash('Database restored — reload to see updated counts') } else { flash('Restore failed', false) }
    } finally { setRestoring(null) }
  }

  const handleDelete = async (filename) => {
    if (!confirm(`Delete backup "${filename}"?`)) return
    const res = await fetch(`/api/backups/${encodeURIComponent(filename)}`, { method: 'DELETE' })
    if (res.ok) { flash('Deleted'); loadBackups() }
  }

  const handleUpload = async (e) => {
    const file = e.target.files?.[0]; if (!file) return
    setUploading(true)
    try {
      const form = new FormData(); form.append('file', file)
      const res = await fetch('/api/backups/upload', { method: 'POST', body: form })
      if (res.ok) { flash('Upload successful'); loadBackups() }
      else { const err = await res.json().catch(() => ({})); flash(err.detail || 'Upload failed', false) }
    } finally { setUploading(false); e.target.value = '' }
  }

  const Pills = ({ options, value, onChange }) => (
    <div className="flex gap-2">
      {options.map(([val, label]) => (
        <button key={val} onClick={() => onChange(val)}
          className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${value === val ? 'bg-blue-600 text-white' : 'bg-bg text-muted hover:text-fg'}`}>
          {label}
        </button>
      ))}
    </div>
  )

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-surface border border-border rounded-xl shadow-2xl w-full max-w-lg mx-4 max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <h2 className="text-base font-semibold text-fg">Database Backups</h2>
          <button onClick={onClose} className="text-subtle hover:text-fg text-lg leading-none">✕</button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
          {/* Actions */}
          <div className="flex items-center gap-3 flex-wrap">
            <button onClick={handleCreate} disabled={creating}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm rounded-lg font-medium transition-colors">
              {creating ? 'Creating…' : 'Backup Now'}
            </button>
            <button onClick={() => fileRef.current?.click()} disabled={uploading}
              className="px-4 py-2 bg-raised hover:bg-elevated disabled:opacity-50 text-secondary text-sm rounded-lg transition-colors">
              {uploading ? 'Uploading…' : 'Upload Backup'}
            </button>
            <input ref={fileRef} type="file" accept=".db" className="hidden" onChange={handleUpload} />
            {msg && <span className={`text-xs ml-auto ${msg.ok ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>{msg.text}</span>}
          </div>

          {/* Settings */}
          <div className="bg-raised rounded-lg p-4 space-y-4">
            <p className="text-xs text-subtle uppercase tracking-wider">Settings</p>

            <div className="flex items-center gap-3">
              <label className="text-sm text-muted shrink-0">Keep</label>
              <input type="number" min={1} max={99} value={sched.keep_n} onChange={(e) => set({ keep_n: Number(e.target.value) })}
                className="w-16 bg-bg border border-border rounded px-2 py-1 text-sm text-fg focus:outline-none focus:border-blue-500" />
              <label className="text-sm text-muted">backups</label>
            </div>

            <label className="flex items-center gap-3 cursor-pointer">
              <div onClick={() => set({ schedule_enabled: !sched.schedule_enabled })}
                className={`relative w-10 h-5 rounded-full transition-colors ${sched.schedule_enabled ? 'bg-blue-600' : 'bg-elevated'}`}>
                <span className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${sched.schedule_enabled ? 'translate-x-5' : 'translate-x-0.5'}`} />
              </div>
              <span className="text-sm text-fg">{sched.schedule_enabled ? 'Automatic backups enabled' : 'Automatic backups disabled'}</span>
            </label>

            <div className={sched.schedule_enabled ? '' : 'opacity-40 pointer-events-none'}>
              <div className="mb-3">
                <p className="text-xs text-subtle mb-2">Frequency</p>
                <Pills options={[['daily','Daily'],['weekly','Weekly'],['monthly','Monthly']]} value={sched.schedule_frequency} onChange={(v) => set({ schedule_frequency: v })} />
              </div>
              {sched.schedule_frequency === 'weekly' && (
                <div className="mb-3">
                  <p className="text-xs text-subtle mb-2">Day of Week</p>
                  <select value={sched.schedule_day_of_week} onChange={(e) => set({ schedule_day_of_week: Number(e.target.value) })} className={SELECT}>
                    {DAYS.map((d, i) => <option key={i} value={i}>{d}</option>)}
                  </select>
                </div>
              )}
              {sched.schedule_frequency === 'monthly' && (
                <div className="mb-3">
                  <p className="text-xs text-subtle mb-2">Day of Month</p>
                  <select value={sched.schedule_day_of_month} onChange={(e) => set({ schedule_day_of_month: Number(e.target.value) })} className={SELECT}>
                    {Array.from({ length: 28 }, (_, i) => i + 1).map((d) => <option key={d} value={d}>{d}</option>)}
                  </select>
                </div>
              )}
              <div className="mb-1">
                <p className="text-xs text-subtle mb-2">Time of Day</p>
                <select value={sched.schedule_hour} onChange={(e) => set({ schedule_hour: Number(e.target.value) })} className={SELECT}>
                  {HOURS.map(({ value, label }) => <option key={value} value={value}>{label}</option>)}
                </select>
              </div>
              {sched.next_run && <p className="text-xs text-subtle mt-2">Next backup: {new Date(sched.next_run).toLocaleString()}</p>}
            </div>

            <button onClick={handleSaveSettings} disabled={savingSettings}
              className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm rounded-lg font-medium transition-colors">
              {savingSettings ? 'Saving…' : 'Save Settings'}
            </button>
          </div>

          {/* Backup list */}
          <div>
            <p className="text-xs text-subtle uppercase tracking-wider mb-2">Backups</p>
            {backups.length === 0 ? (
              <p className="text-sm text-subtle">No backups yet.</p>
            ) : (
              <div className="space-y-1">
                {backups.map((b) => (
                  <div key={b.filename} className="flex items-center gap-2 bg-raised rounded-lg px-3 py-2">
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-mono text-secondary truncate">{b.filename}</p>
                      <p className="text-xs text-subtle">{fmt(b.created_at)} · {fmtSize(b.size)}</p>
                    </div>
                    <button onClick={() => handleDownload(b.filename)} title="Download"
                      className="text-xs px-2 py-1 bg-elevated hover:bg-high text-secondary rounded transition-colors">↓</button>
                    <button onClick={() => handleRestore(b.filename)} disabled={restoring === b.filename} title="Restore"
                      className="text-xs px-2 py-1 bg-yellow-600 hover:bg-yellow-500 disabled:opacity-50 text-white rounded transition-colors">
                      {restoring === b.filename ? '…' : 'Restore'}
                    </button>
                    <button onClick={() => handleDelete(b.filename)} title="Delete"
                      className="text-xs px-2 py-1 bg-red-100 hover:bg-red-200 text-red-700 dark:bg-red-900 dark:hover:bg-red-800 dark:text-red-200 rounded transition-colors">✕</button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="px-5 py-4 border-t border-border flex justify-end">
          <button onClick={onClose} className="px-4 py-2 bg-raised hover:bg-elevated text-fg text-sm rounded-lg transition-colors">Close</button>
        </div>
      </div>
    </div>
  )
}
