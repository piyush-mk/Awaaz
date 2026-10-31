import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const API_TARGET = process.env.API_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: API_TARGET, changeOrigin: true },
      '/r': { target: API_TARGET, changeOrigin: true },
      '/k': { target: API_TARGET, changeOrigin: true },
      '/webhooks': { target: API_TARGET, changeOrigin: true },
    },
  },
})
