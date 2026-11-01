import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'
import fs from 'node:fs'

const pkg = JSON.parse(fs.readFileSync(path.resolve(__dirname, 'package.json'), 'utf8'))

export default defineConfig({
  base: './',
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  resolve: {
    alias: {
      '@rl/core': path.resolve(__dirname, '../../packages/core/src/index.ts'),
    },
  },
  build: {
    target: 'es2020',
    chunkSizeWarningLimit: 2000,
  },
  server: { port: 5173 },
})
