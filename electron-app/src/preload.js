const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  sendCmd: (payload) => {
    return new Promise((resolve) => {
      const id = Math.random().toString(36).slice(2);
      ipcRenderer.once('py-response-' + id, (event, res) => {
        resolve(res);
      });
      ipcRenderer.send('py-request', Object.assign({}, payload, { __id: id }));
    });
  },
  onLog: (cb) => ipcRenderer.on('py-log', (ev, data) => cb(data)),
  onRaw: (cb) => ipcRenderer.on('py-raw', (ev, data) => cb(data)),
  onError: (cb) => ipcRenderer.on('py-error', (ev, data) => cb(data))
});
