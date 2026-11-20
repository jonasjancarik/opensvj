import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Frontend, přihlašovací služba i API jsou pro prohlížeč na jedné adrese,
// takže session cookie funguje bez CORS.
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5180,
    strictPort: true,
    proxy: {
      '/api/auth': 'http://localhost:3010',
      '/api': 'http://localhost:8010',
    },
  },
})
