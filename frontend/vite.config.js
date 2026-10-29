import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/r': { target: 'http://localhost:8000', changeOrigin: true },
      '/k': { target: 'http://localhost:8000', changeOrigin: true },
      '/webhooks': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
