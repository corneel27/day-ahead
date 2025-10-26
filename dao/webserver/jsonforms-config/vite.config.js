import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Configure your Flask backend port here
const FLASK_PORT = process.env.FLASK_PORT || 5000;
const FLASK_HOST = process.env.FLASK_HOST || 'localhost';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  base: '/static/config/',
  build: {
    outDir: '../app/static/config',
    assetsDir: 'assets',
    emptyOutDir: true,
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: `http://${FLASK_HOST}:${FLASK_PORT}`,
        changeOrigin: true,
      },
      '/static': {
        target: `http://${FLASK_HOST}:${FLASK_PORT}`,
        changeOrigin: true,
      }
    }
  }
})
