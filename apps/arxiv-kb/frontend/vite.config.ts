import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/app/arxiv-kb/',
  build: { outDir: 'dist' },
  server: {
    proxy: { '/api': 'http://localhost:8800' },
  },
})
