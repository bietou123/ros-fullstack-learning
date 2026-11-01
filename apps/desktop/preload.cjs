const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('__RL_PLATFORM__', {
  name: 'desktop',
  detectBackend: () => ipcRenderer.invoke('rl:detect'),
  runExperiment: (spec) => ipcRenderer.invoke('rl:runExperiment', spec),
})

contextBridge.exposeInMainWorld('rlDesktop', {
  version: () => ipcRenderer.invoke('rl:version'),
})
