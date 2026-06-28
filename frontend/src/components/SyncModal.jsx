import { useState, useEffect } from 'react'

const ISSUE_LABELS = {
  broken_symlink: { label: 'Broken symlink', desc: 'Symlink target no longer exists', color: 'text-red-500 dark:text-red-400', fixable: true },
  orphaned:       { label: 'Orphaned symlink', desc: 'Not found in VodLink database', color: 'text-orange-500 dark:text-orange-400', fixable: true },
  wrong_target:   { label: 'Wrong target', desc: 'Symlink points to unexpected path', color: 'text-yellow-600 dark:text-yellow-400', fixable: true },
  real_dir:       { label: 'Real directory', desc: 'Not a symlink — manually created, not auto-removed', color: 'text-blue-500 dark:text-blue-400', fixable: false },
}

function IssueGroup({ items, type }) {
  const [expanded, setExpanded] = useState(false)
  if (!items.length) return null
  const meta = ISSUE_LABELS[type]
  return (
    <div className="mb-3">
      <button onClick={() => setExpanded((v) => !v)} className="w-full flex items-center justify-between text-left">
        <span className={`text-sm font-medium ${meta.color}`}>
          {meta.label} ({items.length})
          {meta.fixable && <span className="ml-2 text-xs text-subtle">auto-fixable</span>}
        </span>
        <span className="text-subtle text-xs">{expanded ? '▲' : '▼'}</span>
      </button>
      <p className="text-xs text-subtle mb-1">{meta.desc}</p>
      {expanded && (
        <div className="mt-1 max-h-40 overflow-y-auto bg-bg rounded p-2 space-y-1">
          {items.map((i) => (
            <div key={i.dir_name} className="text-xs text-muted font-mono truncate">
              {i.dir_name}
              {i.target && <span className="text-subtle"> → {i.target}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function SyncModal({ onClose, onFixed }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [fixing, setFixing] = useState(false)
  const [fixResult, setFixResult] = useState(null)

  useEffect(() => {
    fetch('/api/sync/check')
      .then((r) => r.json())
      .then((d) => { setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  const handleFix = async () => {
    setFixing(true)
    try {
      const res = await fetch('/api/sync/fix', { method: 'POST' })
      const result = await res.json()
      setFixResult(result)
      const fresh = await fetch('/api/sync/check').then((r) => r.json())
      setData(fresh)
      onFixed()
    } catch {} finally { setFixing(false) }
  }

  const allIssues = data ? [...data.movies, ...data.series] : []
  const fixableCount = allIssues.filter((i) => ISSUE_LABELS[i.issue]?.fixable).length
  const movieIssues = data?.movies ?? []
  const seriesIssues = data?.series ?? []
  const groupBy = (items, type) => items.filter((i) => i.issue === type)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-surface border border-border rounded-xl shadow-2xl w-full max-w-lg mx-4 max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <h2 className="text-base font-semibold text-fg">Sync Check</h2>
          <button onClick={onClose} className="text-subtle hover:text-fg text-lg leading-none">✕</button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {loading ? (
            <p className="text-subtle text-sm">Scanning destination directories…</p>
          ) : allIssues.length === 0 ? (
            <p className="text-green-600 dark:text-green-400 text-sm">No issues found. Destination directories match the database.</p>
          ) : (
            <>
              <p className="text-sm text-muted mb-4">
                Found <span className="text-fg font-medium">{allIssues.length} issue{allIssues.length !== 1 ? 's' : ''}</span>
                {fixableCount > 0 && <> — {fixableCount} can be auto-fixed</>}
              </p>
              {movieIssues.length > 0 && (
                <div className="mb-4">
                  <p className="text-xs text-subtle uppercase tracking-wider mb-2">Movies</p>
                  {Object.keys(ISSUE_LABELS).map((type) => (
                    <IssueGroup key={type} type={type} items={groupBy(movieIssues, type)} />
                  ))}
                </div>
              )}
              {seriesIssues.length > 0 && (
                <div>
                  <p className="text-xs text-subtle uppercase tracking-wider mb-2">Series</p>
                  {Object.keys(ISSUE_LABELS).map((type) => (
                    <IssueGroup key={type} type={type} items={groupBy(seriesIssues, type)} />
                  ))}
                </div>
              )}
              {fixResult && (
                <div className="mt-4 p-3 bg-raised rounded text-xs text-secondary">
                  Removed {fixResult.removed.length} symlink{fixResult.removed.length !== 1 ? 's' : ''}.
                  {fixResult.errors.length > 0 && <span className="text-red-500 ml-2">{fixResult.errors.length} error{fixResult.errors.length !== 1 ? 's' : ''}.</span>}
                </div>
              )}
            </>
          )}
        </div>

        <div className="px-5 py-4 border-t border-border flex items-center justify-between gap-3">
          <p className="text-xs text-subtle">Real directories are never auto-removed.</p>
          <div className="flex gap-2">
            {!loading && fixableCount > 0 && (
              <button onClick={handleFix} disabled={fixing}
                className="px-4 py-2 bg-yellow-600 hover:bg-yellow-500 disabled:opacity-50 text-white text-sm rounded-lg font-medium transition-colors">
                {fixing ? 'Fixing…' : `Fix ${fixableCount} Issue${fixableCount !== 1 ? 's' : ''}`}
              </button>
            )}
            <button onClick={onClose} className="px-4 py-2 bg-raised hover:bg-elevated text-fg text-sm rounded-lg transition-colors">Close</button>
          </div>
        </div>
      </div>
    </div>
  )
}
