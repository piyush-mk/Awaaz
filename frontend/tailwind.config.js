/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        'paytm-blue': '#00B9F5',
        'paytm-blue-dark': '#0095C8',
        'paytm-orange': '#FF8A1F',
        'paytm-orange-dark': '#E5700A',
        accent: '#FF8A1F',
        ink: '#0E1B33',
        'ink-2': '#1B2330',
        'ink-3': '#46546B',
        'stock-green': '#34C759',
        'stock-yellow': '#FFCC00',
        'stock-red': '#FF3B30',
        'bg-app': '#ECF0F4',
        line: '#DDE3EA',
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', '"Noto Sans Devanagari"', 'system-ui', 'sans-serif'],
        hindi: ['"Noto Sans Devanagari"', '"IBM Plex Sans"', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
      },
    },
  },
  plugins: [],
}
