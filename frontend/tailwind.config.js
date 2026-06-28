/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        bg:        'rgb(var(--c-bg)        / <alpha-value>)',
        surface:   'rgb(var(--c-surface)   / <alpha-value>)',
        raised:    'rgb(var(--c-raised)    / <alpha-value>)',
        elevated:  'rgb(var(--c-elevated)  / <alpha-value>)',
        high:      'rgb(var(--c-high)      / <alpha-value>)',
        border:    'rgb(var(--c-border)    / <alpha-value>)',
        fg:        'rgb(var(--c-fg)        / <alpha-value>)',
        secondary: 'rgb(var(--c-secondary) / <alpha-value>)',
        muted:     'rgb(var(--c-muted)     / <alpha-value>)',
        subtle:    'rgb(var(--c-subtle)    / <alpha-value>)',
      },
    },
  },
  plugins: [],
}
