import { defineConfig } from 'vite'

export default defineConfig({
  base: '/static/build',
  build: {
    outDir: 'app/static/build',
    emptyOutDir: true,
    manifest: true,
    rollupOptions: {
      input: {
        main: 'assets/main.js'
      }
    }
  },
  server: {
    host: 'localhost',
    port: 5173,
    strictPort: true,
    origin: 'http://localhost:5173',
  },
})