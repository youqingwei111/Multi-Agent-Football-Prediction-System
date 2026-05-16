/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        console: {
          bg: '#0d1117',
          panel: '#161b22',
          border: '#30363d',
          green: '#3fb950',
          yellow: '#d29922',
          red: '#f85149',
          blue: '#58a6ff',
          purple: '#bc8cff',
          gray: '#8b949e',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
}