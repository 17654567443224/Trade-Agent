import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: '#0d1117',
          secondary: '#161b22',
          card: '#1c2128',
          border: '#30363d',
        },
        accent: {
          green: '#3fb950',
          red: '#f85149',
          blue: '#58a6ff',
          yellow: '#e3b341',
          purple: '#bc8cff',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
}

export default config
