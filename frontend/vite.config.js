import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发环境：vite dev server 跑在 5173，把后端路径代理到 backend:8080
// 生产环境：本配置只用于 build，产物 dist 由 FastAPI 托管
export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/auth': { target: 'http://backend:8080', changeOrigin: true },
      '/nodes': { target: 'http://backend:8080', changeOrigin: true },
      '/sub': { target: 'http://backend:8080', changeOrigin: true },
      '/api': { target: 'http://backend:8080', changeOrigin: true },
      '/health': { target: 'http://backend:8080', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
