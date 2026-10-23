import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': resolve(__dirname, 'src') },
  },
  build: {
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/echarts') || id.includes('node_modules/vue-echarts')) {
            return 'echarts'
          }
        },
      },
    },
  },
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8506', changeOrigin: true },
    },
  },
})
