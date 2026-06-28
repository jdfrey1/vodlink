import { useState } from 'react'

const PLACEHOLDER = (
  <div className="w-full h-full flex items-center justify-center bg-raised text-subtle">
    <svg className="w-10 h-10" fill="currentColor" viewBox="0 0 24 24">
      <path d="M18 4H6c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm-6 3c1.38 0 2.5 1.12 2.5 2.5S13.38 12 12 12s-2.5-1.12-2.5-2.5S10.62 7 12 7zm5 13H7v-.57c0-.44.2-.86.54-1.13C8.9 17.58 10.37 17 12 17s3.1.58 4.46 1.3c.34.27.54.69.54 1.13V20z" />
    </svg>
  </div>
)

export default function MediaCard({ item, onLinkToggle }) {
  const [busy, setBusy] = useState(false)
  const [imgErr, setImgErr] = useState(false)

  const handleClick = async () => {
    setBusy(true)
    try { await onLinkToggle(item.linked) }
    finally { setBusy(false) }
  }

  const tmdbUrl = `https://www.themoviedb.org/${item.type === 'movie' ? 'movie' : 'tv'}/${item.tmdb_id}`

  return (
    <div className="bg-surface rounded-lg overflow-hidden flex flex-col border border-border">
      <a href={tmdbUrl} target="_blank" rel="noreferrer" className="relative aspect-[2/3] block">
        {item.thumb_url && !imgErr ? (
          <img src={item.thumb_url} alt={item.title}
            className="w-full h-full object-cover" loading="lazy"
            onError={() => setImgErr(true)} />
        ) : PLACEHOLDER}
        {item.linked && (
          <span className="absolute top-1.5 right-1.5 bg-green-500 rounded-full p-0.5">
            <svg className="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 24 24">
              <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z" />
            </svg>
          </span>
        )}
      </a>

      <div className="p-2 flex flex-col gap-1 flex-1">
        <p className="text-xs font-medium leading-tight line-clamp-2 text-fg">{item.title}</p>
        <p className="text-xs text-muted">{item.year || '—'}</p>
        {item.genres && (
          <p className="text-xs text-subtle line-clamp-1">
            {item.genres.split(',').slice(0, 2).join(', ')}
          </p>
        )}
        {item.rating > 0 && (
          <p className="text-xs text-yellow-500 dark:text-yellow-400">★ {item.rating.toFixed(1)}</p>
        )}
        <button onClick={handleClick} disabled={busy}
          className={`mt-auto text-xs py-1.5 rounded font-medium transition-colors disabled:opacity-50 ${
            item.linked
              ? 'bg-red-100 hover:bg-red-200 text-red-700 dark:bg-red-900 dark:hover:bg-red-800 dark:text-red-100'
              : 'bg-blue-600 hover:bg-blue-500 text-white'
          }`}>
          {busy ? '…' : item.linked ? 'Unlink' : 'Link'}
        </button>
      </div>
    </div>
  )
}
