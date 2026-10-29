import {defineConfig, loadEnv} from 'vite'
import react from '@vitejs/plugin-react'
import {fileURLToPath} from 'node:url'

const workspaceRoot = fileURLToPath(new URL('..', import.meta.url))
const sharedPublic = fileURLToPath(new URL('../frontend/public', import.meta.url))

export default defineConfig(({mode}) => {
  const env = loadEnv(mode, '.', ['AGRISCAN_', 'VITE_'])
  const apiTarget = process.env.AGRISCAN_API_PROXY || process.env.AGRISCAN_API_TARGET || env.AGRISCAN_API_PROXY || env.AGRISCAN_API_TARGET || 'http://127.0.0.1:18000'
  const proxy = {'/api': apiTarget, '/uploads': apiTarget, '/docs': apiTarget, '/openapi.json': apiTarget, '/redoc': apiTarget}
  const base = process.env.VITE_ADMIN_BASE || env.VITE_ADMIN_BASE || (mode === 'production' ? '/admin/' : '/')
  return {
    plugins: [{name:'agriscan-public-path',enforce:'pre',transform(code,id) {
      if (base === '/' || !/[/\\](frontend|admin)[/\\]src[/\\].*\.[jt]sx?$/.test(id)) return
      return code.replace(/(["'`])\/(images|brand)\//g, `$1${base.replace(/\/+$/, '')}/$2/`)
    }}, react()],
    base,
    publicDir: sharedPublic,
    define: {'import.meta.env.VITE_APP_SURFACE': JSON.stringify('admin')},
    resolve: {dedupe: ['react', 'react-dom']},
    build: {rollupOptions: {output: {manualChunks: {charts: ['recharts']}}}},
    server: {port: 5175, strictPort: true, fs: {allow: [workspaceRoot]}, proxy},
    preview: {port: 4175, strictPort: true, proxy},
  }
})
