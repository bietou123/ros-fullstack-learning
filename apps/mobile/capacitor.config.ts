import type { CapacitorConfig } from '@capacitor/cli'

const config: CapacitorConfig = {
  appId: 'com.rosfullstack.learning',
  appName: '工业机器人全栈学习',
  webDir: '../web/dist',
  android: {
    allowMixedContent: false,
    backgroundColor: '#0d1117',
  },
  server: {
    androidScheme: 'https',
  },
}

export default config
