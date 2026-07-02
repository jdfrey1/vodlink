import { useState, useEffect } from 'react'

export default function ConnectionModal({ onClose }) {
  const [dispatcharrUrl, setDispatcharrUrl] = useState('')
  const [envUrl, setEnvUrl] = useState('')
  const [testStatus, setTestStatus] = useState(null) // null | 'testing' | 'ok' | 'fail'
  const [testError, setTestError] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    fetch('/api/settings')
      .then((r) => r.json())
      .then((d) => {
        setDispatcharrUrl(d.dispatcharr_url_effective || '')
        setEnvUrl(d.dispatcharr_url_env || '')
      })
      .catch(() => {})
  }, [])

  const handleTest = async () => {
    setTestStatus('testing')
    setTestError('')
    try {
      const r = await fetch('/api/settings/test-dispatcharr', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dispatcharr_url: dispatcharrUrl }),
      })
      const d = await r.json()
      setTestStatus(d.ok ? 'ok' : 'fail')
      if (!d.ok) setTestError(d.error || `HTTP ${d.status_code}`)
    } catch (e) {
      setTestStatus('fail')
      setTestError(String(e))
    }
  }

  const handleSave = async () => {
    setSaving(true)
    setSaved(false)
    try {
      await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dispatcharr_url: dispatcharrUrl }),
      })
      setSaved(true)
    } catch {} finally {
      setSaving(false)
    }
  }

  const statusIcon = () => {
    if (testStatus === 'testing') return <span className="text-yellow-400 animate-pulse">Testing…</span>
    if (testStatus === 'ok') return <span className="text-green-500">&#10003; Connected</span>
    if (testStatus === 'fail') return <span className="text-red-500">&#10007; {testError}</span>
    return null
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-surface border border-border rounded-xl shadow-2xl w-full max-w-md p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold">Connection Settings</h2>
          <button onClick={onClose} className="text-muted hover:text-fg transition-colors text-lg leading-none">&times;</button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-xs text-muted mb-1">Dispatcharr URL</label>
            <input
              type="text"
              value={dispatcharrUrl}
              onChange={(e) => { setDispatcharrUrl(e.target.value); setTestStatus(null); setSaved(false) }}
              placeholder="http://192.168.40.80:9191"
              className="w-full bg-raised border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500 font-mono"
            />
            {envUrl && envUrl !== dispatcharrUrl && (
              <p className="text-xs text-muted mt-1">
                Env var: <span className="font-mono text-subtle">{envUrl}</span>
                {' '}
                <button
                  onClick={() => { setDispatcharrUrl(envUrl); setTestStatus(null) }}
                  className="text-blue-400 hover:underline"
                >use</button>
              </p>
            )}
            <p className="text-xs text-subtle mt-1">
              Internal URL VodLink uses to reach Dispatcharr. Use the macvlan/container IP, not the host IP.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={handleTest}
              disabled={!dispatcharrUrl || testStatus === 'testing'}
              className="px-4 py-2 text-sm bg-raised border border-border rounded-lg hover:bg-elevated disabled:opacity-40 transition-colors"
            >
              Test Connection
            </button>
            <span className="text-sm">{statusIcon()}</span>
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <button onClick={onClose} className="px-4 py-2 text-sm text-muted hover:text-fg transition-colors">
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-500 text-white rounded-lg disabled:opacity-40 transition-colors"
          >
            {saving ? 'Saving…' : saved ? 'Saved ✓' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}
