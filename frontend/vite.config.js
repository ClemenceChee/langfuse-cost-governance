import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // Dev-only proxy; in Docker, nginx proxies /api -> api service.
    proxy: { '/api': 'http://localhost:8000' },
  },
})
