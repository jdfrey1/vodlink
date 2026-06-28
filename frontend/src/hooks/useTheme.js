import { useState, useEffect } from 'react'

const KEY = 'vodlink.theme'

function resolveTheme(theme) {
  if (theme === 'system') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  return theme
}

function applyTheme(theme) {
  document.documentElement.classList.toggle('dark', resolveTheme(theme) === 'dark')
}

export function useTheme() {
  const [theme, setTheme] = useState(() => {
    try { return localStorage.getItem(KEY) || 'system' } catch { return 'system' }
  })

  useEffect(() => {
    applyTheme(theme)
    try { localStorage.setItem(KEY, theme) } catch {}
  }, [theme])

  // Reapply when system preference changes (only matters in system mode)
  useEffect(() => {
    if (theme !== 'system') return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = () => applyTheme('system')
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [theme])

  // Cycles: system → light → dark → system
  const cycleTheme = () => setTheme((t) => t === 'system' ? 'light' : t === 'light' ? 'dark' : 'system')

  return { theme, setTheme, cycleTheme }
}
