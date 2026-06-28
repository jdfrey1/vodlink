import { useState } from 'react'

const SCAN_ACTIONS = [
  { label: 'Scan Movies', path: 'movies' },
  { label: 'Scan Series', path: 'series' },
  { label: 'Scan All', path: 'all' },
  { label: 'Full Rescan', path: 'all?full=true' },
]

function fmt(ts) {
  if (!ts) return 'never'
  return new Date(ts * 1000).toLocaleString()
}

export default function ScanStatus({ status, version, onScan, onSyncCheck, onSchedule, onBackups }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="relative shrink-0">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 text-sm text-muted hover:text-fg bg-raised hover:bg-elevated px-3 py-1.5 rounded-lg transition-colors"
      >
        <span className={`w-2 h-2 rounded-full ${status.running ? 'bg-yellow-400 animate-pulse' : 'bg-green-400'}`} />
        {status.running ? (
          <span>
            Scanning {status.current_type === 'movie' ? 'movies' : 'series'}
            {status.total > 0 && (
              <span className="ml-1 text-xs opacity-70">
                {status.progress.toLocaleString()}/{status.total.toLocaleString()}
              </span>
            )}
          </span>
        ) : 'Library'}
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute right-0 mt-2 w-56 bg-raised border border-border rounded-lg shadow-2xl z-20">
            <div className="p-3 text-xs text-muted border-b border-border space-y-0.5">
              <div>Movies: {status.movie_count?.toLocaleString() ?? '—'}</div>
              <div>Series: {status.series_count?.toLocaleString() ?? '—'}</div>
              <div className="pt-1 text-subtle">Last movie scan: {fmt(status.last_scan_movies)}</div>
              <div className="text-subtle">Last series scan: {fmt(status.last_scan_series)}</div>
              {version && <div className="pt-1 text-subtle/60">v{version}</div>}
            </div>
            <div className="p-1">
              {SCAN_ACTIONS.map(({ label, path }) => (
                <button
                  key={path}
                  onClick={() => { onScan(path); setOpen(false) }}
                  disabled={status.running}
                  className="w-full text-left px-3 py-2 text-sm text-secondary hover:bg-elevated rounded disabled:opacity-40 transition-colors"
                >
                  {label}
                </button>
              ))}
              <div className="border-t border-border mt-1 pt-1">
                <button onClick={() => { onSyncCheck(); setOpen(false) }}
                  className="w-full text-left px-3 py-2 text-sm text-yellow-500 dark:text-yellow-400 hover:bg-elevated rounded transition-colors">
                  Sync Check
                </button>
                <button onClick={() => { onSchedule(); setOpen(false) }}
                  className="w-full text-left px-3 py-2 text-sm text-blue-500 dark:text-blue-400 hover:bg-elevated rounded transition-colors">
                  Schedule Scans
                </button>
                <button onClick={() => { onBackups(); setOpen(false) }}
                  className="w-full text-left px-3 py-2 text-sm text-blue-500 dark:text-blue-400 hover:bg-elevated rounded transition-colors">
                  Backups
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
