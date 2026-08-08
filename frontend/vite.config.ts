import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  // Electron production renderer is loaded with file://, so assets must be relative.
  base: './',
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    outDir: 'dist-frontend',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    strictPort: true,
  },
})