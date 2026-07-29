import path from 'node:path'
import { configDefaults, defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    proxy: {
      '/health': 'http://localhost:8000',
      '/api': 'http://localhost:8000',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/setupTests.ts',
    // e2e/**/*.spec.ts are Playwright specs (run via `make test-e2e`, not
    // Vitest) - without this exclusion Vitest tries to execute them too and
    // fails, since they import `test`/`expect` from @playwright/test.
    exclude: [...configDefaults.exclude, 'e2e/**'],
  },
})
