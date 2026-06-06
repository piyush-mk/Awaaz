/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        'paytm-blue': '#00B9F5',
        'paytm-blue-dark': '#0095C8',
        'paytm-orange': '#FF6F00',
        'paytm-orange-dark': '#E65100',
        'stock-green': '#34C759',
        'stock-yellow': '#FFCC00',
        'stock-red': '#FF3B30',
        'bg-app': '#F5F7FA',
      },
      fontFamily: {
        hindi: ['Noto Sans Devanagari', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
