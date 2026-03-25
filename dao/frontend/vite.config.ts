import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    // Output directory for production build
    outDir: 'dist',
    // Enable source maps for development only
    sourcemap: false,
    // Asset optimization
    minify: 'esbuild',
    rollupOptions: {
      output: {
        // Manual chunk splitting for better caching
        manualChunks: {
          'react-vendor': ['react', 'react-dom'],
          'mui-vendor': ['@mui/material', '@mui/icons-material'],
          'jsonforms-vendor': ['@jsonforms/core', '@jsonforms/react', '@jsonforms/material-renderers'],
        },
      },
    },
    // Compression settings
    chunkSizeWarningLimit: 1000,
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
