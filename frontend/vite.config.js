import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 后端地址：本地默认 5001（见 README「快速开始」）；可用环境变量 VITE_API_TARGET 覆盖
// （例如公网演示站把后端跑在别的端口时，构建/预览时指定即可）
const API_TARGET = process.env.VITE_API_TARGET || 'http://localhost:5001'
const proxy = {
  '/api': {
    target: API_TARGET,
    changeOrigin: true
  }
}

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: false,
    allowedHosts: true,
    proxy
  },
  // 公网演示用：先 `npm run build`，再 `npm run preview` 提供生产包（同样代理 /api）
  preview: {
    host: '0.0.0.0',
    port: 4173,
    strictPort: false,
    allowedHosts: true,
    proxy
  }
})
