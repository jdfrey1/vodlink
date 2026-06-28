export default function SearchBar({ value, onChange, placeholder }) {
  return (
    <input
      type="text"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-full bg-raised border border-border rounded-lg px-4 py-2 text-sm text-fg placeholder-subtle focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors"
    />
  )
}
