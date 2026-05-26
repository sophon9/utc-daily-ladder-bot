import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0', // Allow access from LAN
    port: 3030,
    proxy: {
      '/api': {
        target: 'http://localhost:8030',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8030',
        ws: true,
      },
    },
  },
})
