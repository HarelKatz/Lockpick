import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 600,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        // Overridable so the e2e harness can point the dev server at an
        // isolated backend port; defaults to the standard dev backend.
        target: process.env.API_PROXY_TARGET || 'http://localhost:8000',
        changeOrigin: true,
        // Required for the live-push socket (/api/ops/{id}/ws). Without it Vite
        // proxies the HTTP calls but silently drops the WebSocket upgrade, so
        // dev sits on "Connecting…" forever and no broadcast (Rule #18) ever
        // lands. Production nginx sets the Upgrade headers itself and was fine,
        // which is why this only ever bit local dev.
        ws: true,
      },
    },
  },
})
