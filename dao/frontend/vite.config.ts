import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/config/',  // Set base path for production assets
  build: {
    // Output directory for production build
    outDir: 'dist',
    // Enable source maps for development only
    sourcemap: false,
    // Asset optimization
    minify: 'esbuild',
    rollupOptions: {
      output: {
        // Disable code splitting to avoid chunk loading order issues
        // All code will be in a single bundle
        manualChunks: undefined,
      },
    },
    // Compression settings
    chunkSizeWarningLimit: 2000, // Increased since we're bundling everything
  },
  server: {
    // Enable source maps for development
    sourcemap: true,
    proxy: {
      // Proxy all API v2 calls to backend during development
      // In production, these are handled by the Flask backend
      '/api/v2': {
        target: 'http://localhost:5000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
