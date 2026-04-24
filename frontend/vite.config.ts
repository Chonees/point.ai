/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(async () => {
  const plugins = [react()]

  if (!process.env.VITEST) {
    const tailwindcss = (await import('@tailwindcss/vite')).default
    plugins.push(tailwindcss())
  }

  return {
    plugins,
    server: {
      proxy: {
        '/api': 'http://localhost:8000',
        '/artifacts': 'http://localhost:8000',
        '/downloads': 'http://localhost:8000',
      },
    },
    build: {
      outDir: 'dist',
      emptyOutDir: true,
    },
    test: {
      globals: true,
      environment: 'happy-dom',
      setupFiles: ['./src/test/setup.ts'],
    },
  }
})
