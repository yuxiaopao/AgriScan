import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({mode}) => {
  const env = loadEnv(mode, '.', ['AGRISCAN_', 'VITE_'])
  const apiTarget = env.AGRISCAN_API_TARGET || 'http://127.0.0.1:18000'
  const base = env.VITE_WEB_BASE || '/'
  return {
  base,
  plugins: [{name:'agriscan-public-path',enforce:'pre',transform(code,id) {
    if (base === '/' || !/[/\\](frontend|admin)[/\\]src[/\\].*\.[jt]sx?$/.test(id)) return
    return code.replace(/(["'`])\/(images|brand)\//g, `$1${base.replace(/\/+$/, '')}/$2/`)
  }}, react()],
  build: {rollupOptions: {output: {manualChunks: {'charts': ['recharts']}}}},
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': apiTarget,
      '/uploads': apiTarget,
      '/docs': apiTarget,
      '/openapi.json': apiTarget,
      '/redoc': apiTarget,
    },
  },
  }
})
