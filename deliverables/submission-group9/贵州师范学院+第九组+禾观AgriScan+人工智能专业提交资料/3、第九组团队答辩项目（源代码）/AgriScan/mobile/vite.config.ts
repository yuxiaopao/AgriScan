import {defineConfig, loadEnv} from 'vite'
import react from '@vitejs/plugin-react'
export default defineConfig(({mode}) => {
  const env = loadEnv(mode, '.', 'AGRISCAN_')
  const target = process.env.AGRISCAN_API_PROXY || env.AGRISCAN_API_PROXY || process.env.AGRISCAN_API_TARGET || env.AGRISCAN_API_TARGET || 'http://127.0.0.1:18000'
  const proxy = {'/api': {target, changeOrigin:true}}
  return {plugins:[react()],server:{host:'127.0.0.1',port:5174,strictPort:true,proxy},preview:{port:4174,proxy},build:{target:'es2022'}}
})
