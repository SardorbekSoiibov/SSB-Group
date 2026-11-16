const TITLE_BAR_HEIGHT = 48;
const { app, BrowserWindow, BrowserView, ipcMain, shell, Notification, session } = require('electron');
const { autoUpdater } = require('electron-updater');
const fs = require('node:fs');
const path = require('node:path');
let window, content, config, polling, loadFailed=false;
const smoke = process.argv.includes('--smoke-test');
const qaHidden = process.argv.includes('--qa-hidden');
const root = process.argv.find(value => value.startsWith('--smoke-root='));
if (root) app.setPath('userData', root.slice('--smoke-root='.length));
const seen = new Set(); let initializedNotifications = false, notificationUser = null, notificationCursor = null, notificationPolling = false;
const configFile = () => path.join(app.getPath('userData'), 'window.json');
function readConfig() { try { return JSON.parse(fs.readFileSync(configFile(), 'utf8')); } catch { return {}; } }
function writeConfig() { try { fs.writeFileSync(configFile(), JSON.stringify(config)); } catch {} }
function validEndpoint(raw) {
  const url = new URL(raw);
  if (url.username || url.password || url.hash || url.search) throw Error('Server manzili noto‘g‘ri.');
  if (url.protocol !== 'https:' && !(url.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname))) throw Error('Server HTTPS bo‘lishi kerak. HTTP faqat lokal sinovda ishlaydi.');
  return url.origin;
}
function layout() { if (!window || !content) return; const [width, height] = window.getContentSize(); content.setBounds({ x: 0, y: TITLE_BAR_HEIGHT, width, height: Math.max(0, height - TITLE_BAR_HEIGHT) }); }
function status(value) { if (window && !window.isDestroyed()) { if (['setup','loading','offline'].includes(value.state)) window.setBrowserView(null); if (value.state==='connected') {window.setBrowserView(content);layout();} window.webContents.send('connection', value); } }
function connect() {
  const base = config.server;
  if (!base) { status({ state: 'setup' }); return; }
  status({ state: 'loading', server: base });
  content.webContents.loadURL(base + '/management/hisob/kirish/').catch(() => status({ state: 'offline', server: base }));
}
function trusted(event) { return event.sender === window.webContents; }
// Ilova faqat boshqaruv tizimini ko'rsatadi: shu serverning /management/ (va uning fayllari) manzillari.
const APP_PATHS = ['/management/', '/static/', '/media/', '/favicon.ico'];
function inApp(target) { return target.origin === config.server && APP_PATHS.some(prefix => target.pathname.startsWith(prefix)); }
app.whenReady().then(() => {
  if(process.platform==='win32')app.setAppUserModelId('uz.ssbgroup.management');
  config = readConfig();
  if (config.server) { try { config.server = validEndpoint(config.server); } catch { delete config.server; } }
  window = new BrowserWindow({ show: !smoke && !qaHidden, width: config.width || 1400, height: config.height || 900, minWidth: 960, minHeight: 650, frame: false,
    title: 'SSB Boshqaruv', backgroundColor: '#f5f5f5', icon: path.join(__dirname, 'icon.ico'),
    webPreferences: { preload: path.join(__dirname, 'bridge.cjs'), contextIsolation: true, nodeIntegration: false, sandbox: true } });
  content = new BrowserView({ webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true, partition: 'persist:ssb-workspace' } });
  layout();
  // Accounts without screenshot permission: Windows itself keeps this window out of captures and recordings.
  content.webContents.on('did-finish-load', async () => {
    try {
      const blocked = await content.webContents.executeJavaScript("document.body?.dataset.screenshots==='blocked'");
      if (window && !window.isDestroyed()) window.setContentProtection(blocked === true);
      if (qaHidden) fs.writeFileSync(path.join(app.getPath('userData'), 'capture-state.json'), JSON.stringify({ blocked, url: content.webContents.getURL(), protected: window.isContentProtected?.() }));
    } catch {}
  });
  content.webContents.session.setPermissionRequestHandler((_wc, _permission, callback) => callback(false));
  content.webContents.session.on('will-download', (event, item) => {
    if (!config.server || item.getURLChain().some(raw => { try { return new URL(raw).origin !== config.server; } catch { return true; } })) { event.preventDefault(); return; }
    item.setSaveDialogOptions({ title: 'Faylni saqlash', defaultPath: path.join(app.getPath('downloads'), path.basename(item.getFilename())) });
    const update = (state, percent=0) => { if (!window.isDestroyed()) window.webContents.send('download-state',{state,percent}); };
    item.on('updated', (_event,state) => update(state==='interrupted'?'interrupted':'progress',Math.round(100*item.getReceivedBytes()/Math.max(1,item.getTotalBytes()))));
    item.once('done', (_event,state) => update(state));
  });
  content.webContents.setUserAgent(content.webContents.getUserAgent() + ' SSBDesktop/' + app.getVersion());
  content.webContents.setWindowOpenHandler(({ url }) => {
    try { const target = new URL(url); if (inApp(target)) content.webContents.loadURL(target.href); else if (target.protocol === 'https:' || target.origin === config.server) shell.openExternal(target.href); } catch {}
    return { action: 'deny' };
  });
  // Boshqaruvdan tashqaridagi sahifa (ommaviy sayt yoki boshqa domen) ilova ichida emas, oddiy brauzerda ochiladi.
  content.webContents.on('will-navigate', (event, url) => {
    try { const target = new URL(url); if (!inApp(target)) { event.preventDefault(); if (target.protocol === 'https:' || target.origin === config.server) shell.openExternal(target.href); } } catch { event.preventDefault(); }
  });
  // Server yo'naltirishi saytga olib borsa (masalan, eski versiyada hisobdan chiqqach) — boshqaruvga qaytariladi.
  content.webContents.on('will-redirect', (event, url) => {
    try { const target = new URL(url); if (target.origin === config.server && !inApp(target)) { event.preventDefault(); content.webContents.loadURL(config.server + '/management/'); } } catch {}
  });
  // Keep the current view attached during ordinary page navigation. Only
  // initial connection/retry uses the full connection screen via connect().
  content.webContents.on('did-start-loading', () => { loadFailed = false; });
  content.webContents.on('did-stop-loading', () => { if (!loadFailed && content.webContents.getURL().startsWith(config.server || 'NONE')) status({ state: 'connected', server: config.server }); });
  content.webContents.on('did-fail-load', (_event, code, _description, _url, mainFrame) => { if (mainFrame && code !== -3) {loadFailed=true;status({ state: 'offline', server: config.server });} });
  window.on('resize', layout);
  window.on('close', () => { const bounds = window.getNormalBounds(); config.width = bounds.width; config.height = bounds.height; writeConfig(); clearInterval(polling); });
  window.loadFile('chrome.html').then(async () => {
    if (smoke) {
      try {
        status({state:'setup'});
        if (validEndpoint('http://127.0.0.1:8000') !== 'http://127.0.0.1:8000') throw Error('Endpoint');
        let blocked = false; try { validEndpoint('http://example.com'); } catch { blocked = true; }
        if (!blocked) throw Error('Insecure endpoint accepted');
        await new Promise(resolve => setTimeout(resolve, 150));
        const shellOK = await window.webContents.executeJavaScript("!!window.ssbDesktop && document.title.includes('SSB') && document.querySelector('#status').textContent === 'Serverni sozlash'");
        if (!shellOK) throw Error('Preload or shell failed');
        status({state:'setup'});
        const localStateOK = await window.webContents.executeJavaScript("!document.querySelector('#connect').hidden && document.querySelector('#status').textContent === 'Serverni sozlash'");
        if (!localStateOK) throw Error('Shell script failed to handle connection state');
        await content.webContents.loadURL('http://127.0.0.1:8000/management/hisob/kirish/');
        const loginOK = await content.webContents.executeJavaScript("!!document.querySelector('input[name=username]') && !window.require");
        if (!loginOK) throw Error('Shared authentication page failed');
        // Regression: switching pages must never detach the workspace view.
        config.server = 'http://127.0.0.1:8000';
        status({state:'connected',server:config.server});
        let detachedDuringNavigation = false;
        const checkAttached = () => { if (window.getBrowserView() !== content) detachedDuringNavigation = true; };
        content.webContents.on('did-start-loading', checkAttached);
        await content.webContents.loadURL(config.server + '/management/hisob/kirish/?desktop-navigation-check=1');
        content.webContents.removeListener('did-start-loading', checkAttached);
        if (detachedDuringNavigation || window.getBrowserView() !== content) throw Error('Workspace detached during navigation');
        fs.writeFileSync(path.join(app.getPath('userData'), 'smoke-result.json'), JSON.stringify({ok:true,packaged:app.isPackaged,version:app.getVersion(),sharedLogin:true,sandbox:true,navigationAttached:true}));
        app.quit();
      } catch (error) {
        fs.writeFileSync(path.join(app.getPath('userData'), 'smoke-result.json'), JSON.stringify({ok:false,error:String(error)}));
        app.exit(1);
      }
    } else if (config.server) connect(); else status({ state: 'setup' });
  });
  if (config.maximized) window.maximize();
  window.on('maximize', () => { config.maximized = true; }); window.on('unmaximize', () => { config.maximized = false; });
  ipcMain.on('window-action', (event, action) => { if (!trusted(event)) return; if (action === 'minimize') window.minimize(); if (action === 'maximize') window.isMaximized() ? window.unmaximize() : window.maximize(); if (action === 'close') window.close(); });
  ipcMain.handle('server-config', (event, raw) => { if (!trusted(event)) throw Error('Denied'); config.server = validEndpoint(raw); writeConfig(); seen.clear(); initializedNotifications = false; notificationCursor = null; notificationUser = null; connect(); return true; });
  ipcMain.on('retry', event => { if (trusted(event)) connect(); });
  ipcMain.on('settings', event => { if (trusted(event)) { window.setBrowserView(null); content.setBounds({ x: 0, y: TITLE_BAR_HEIGHT, width: 0, height: 0 }); status({ state: 'setup', server: config.server }); } });
  ipcMain.on('show-content', event => { if (trusted(event)) { window.setBrowserView(content); layout(); } });
  polling = setInterval(async () => {
    if (notificationPolling || !content || content.webContents.isDestroyed() || !config.server || !content.webContents.getURL().startsWith(config.server + '/management/')) return;
    notificationPolling = true;
    try {
      const endpoint = '/management/enterprise/api/notifications/' + (notificationCursor === null ? '' : '?after=' + notificationCursor);
      const data = await content.webContents.executeJavaScript(`fetch(${JSON.stringify(endpoint)},{credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(10000)}).then(r=>[401,403].includes(r.status)?null:r.ok?r.json():Promise.reject(Error('Unavailable')))`);
      if (!data || !Array.isArray(data.items)) { seen.clear(); initializedNotifications=false; notificationUser=null; notificationCursor=null; return; }
      if (notificationUser !== data.user) { seen.clear(); initializedNotifications=false; notificationUser=data.user; }
      for (const item of data.items) {
        if (!seen.has(item.id) && initializedNotifications && Notification.isSupported()) {
          const alert = new Notification({ title: String(item.title).slice(0, 200), body: String(item.body).slice(0, 500), icon: path.join(__dirname, 'icon.ico') });
          alert.on('click', () => { window.show(); window.focus(); try { const target = new URL(item.url, config.server); if (target.origin === config.server) content.webContents.loadURL(target.href); } catch {} }); alert.show();
        }
        seen.add(item.id);
      }
      initializedNotifications = true;
      notificationCursor = data.cursor;
      if (seen.size > 2000) { const recent = [...seen].slice(-1000); seen.clear(); recent.forEach(id => seen.add(id)); }
    } catch { /* Navigation can destroy the polling execution context. A real
      main-frame failure is handled by did-fail-load, not notification polling. */ }
    finally { notificationPolling = false; }
  }, 20000);
  // Update feed is optional, HTTPS-only, and carries no backend credentials.
  const feed = process.env.SSB_UPDATE_FEED;
  if (app.isPackaged && feed && feed.startsWith('https://')) {
    autoUpdater.setFeedURL({ provider: 'generic', url: feed }); autoUpdater.autoDownload = false;
    autoUpdater.on('error', () => status({state:'update_error',server:config.server})); autoUpdater.on('update-available', () => status({ state: 'update_available', server: config.server }));
    ipcMain.handle('download-update', event => { if (!trusted(event)) throw Error('Denied'); return autoUpdater.downloadUpdate(); });
    autoUpdater.on('update-downloaded', () => status({ state: 'update_ready', server: config.server }));
    ipcMain.on('install-update', event => { if (trusted(event)) autoUpdater.quitAndInstall(); });
    autoUpdater.checkForUpdates().catch(() => {});
  }
});
app.on('window-all-closed', () => app.quit());
