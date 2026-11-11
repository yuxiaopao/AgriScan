import type {CapacitorConfig} from '@capacitor/cli'

const config: CapacitorConfig = {
  appId: 'cn.agriscan.mobile',
  appName: '禾观',
  webDir: 'dist',
  server: {androidScheme: 'https'},
  android: {
    backgroundColor: '#f7f8f2',
    allowMixedContent: process.env.AGRISCAN_DEV_HTTP === '1',
  },
}

export default config
