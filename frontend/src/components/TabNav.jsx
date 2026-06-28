export default function TabNav({ active, onChange, counts }) {
  const tabs = [
    { id: 'movie', label: 'Movies', count: counts.movie },
    { id: 'series', label: 'Series', count: counts.series },
  ]

  return (
    <div className="flex gap-1 bg-raised rounded-lg p-1 w-fit">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
            active === tab.id
              ? 'bg-blue-600 text-white'
              : 'text-muted hover:text-fg'
          }`}
        >
          {tab.label}
          {tab.count != null && tab.count > 0 && (
            <span className="ml-1.5 text-xs opacity-60">{tab.count.toLocaleString()}</span>
          )}
        </button>
      ))}
    </div>
  )
}
