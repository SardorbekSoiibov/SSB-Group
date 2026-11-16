const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('ssbDesktop', Object.freeze({
  action: action => { if (['minimize','maximize','close'].includes(action)) ipcRenderer.send('window-action',action); },
  connect: address => ipcRenderer.invoke('server-config',String(address)),
  retry: () => ipcRenderer.send('retry'), settings: () => ipcRenderer.send('settings'),
  showContent: () => ipcRenderer.send('show-content'),
  downloadUpdate: () => ipcRenderer.invoke('download-update'), installUpdate: () => ipcRenderer.send('install-update'),
  onConnection: callback => ipcRenderer.on('connection',(_event,state)=>callback(state)),
  onDownload: callback => ipcRenderer.on('download-state',(_event,state)=>callback(state)),
}));
