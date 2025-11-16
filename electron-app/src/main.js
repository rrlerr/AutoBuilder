const { app, BrowserWindow, ipcMain, Menu } = require('electron');
const path = require('path');
const isDev = require('electron-is-dev');
const { spawn } = require('child_process');
const { autoUpdater } = require('electron-updater');

let mainWindow = null;
let pyProc = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1100,
    height: 760,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true
    }
  });

  mainWindow.loadFile(path.join(__dirname, '../public/index.html'));
  if (isDev) mainWindow.webContents.openDevTools();

  const template = [
    {
      label: "Tools",
      submenu: [
        {
          label: "AI Update Manager",
          click() {
            mainWindow.loadFile(path.join(__dirname, '../public/update-panel.html'));
          }
        }
      ]
    }
  ];
  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);

  // Auto-update check in packaged app
  if (!isDev) {
    autoUpdater.checkForUpdatesAndNotify();
  }
}

function startPython() {
  if (pyProc) return;
  const script = path.join(__dirname, '../../python-worker/worker.py');
  // Use 'python' — ensure Python 3 is on PATH
  pyProc = spawn('python', [script], { stdio: ['pipe', 'pipe', 'pipe'] });

  pyProc.stdout.on('data', (data) => {
    const lines = data.toString().split('\n').filter(Boolean);
    lines.forEach((line) => {
      try {
        const obj = JSON.parse(line);
        // if it has __id - forward to renderer
        if (obj.__id && mainWindow) {
          mainWindow.webContents.send('py-response-' + obj.__id, obj);
        } else if (mainWindow) {
          // general logs
          mainWindow.webContents.send('py-log', obj);
        }
      } catch (e) {
        // not JSON - log raw
        if (mainWindow) mainWindow.webContents.send('py-raw', line);
      }
    });
  });

  pyProc.stderr.on('data', (d) => {
    if (mainWindow) mainWindow.webContents.send('py-err', d.toString());
  });

  pyProc.on('close', (code) => {
    if (mainWindow) mainWindow.webContents.send('py-exit', code);
    pyProc = null;
  });
}

app.whenReady().then(() => {
  createWindow();
  startPython();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (pyProc) pyProc.kill();
  if (process.platform !== 'darwin') app.quit();
});

// IPC receive JSON requests from renderer; forward to python
ipcMain.on('py-request', (event, data) => {
  if (!pyProc) {
    event.reply('py-error', { ok: false, error: 'Python backend not running' });
    return;
  }
  try {
    pyProc.stdin.write(JSON.stringify(data) + '\n');
  } catch (e) {
    event.reply('py-error', { ok: false, error: String(e) });
  }
});
