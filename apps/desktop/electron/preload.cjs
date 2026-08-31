const { contextBridge, ipcRenderer, webUtils } = require('electron')

contextBridge.exposeInMainWorld('wingDesktop', {
  getConnection: profile => ipcRenderer.invoke('wing:connection', profile),
  revalidateConnection: () => ipcRenderer.invoke('wing:connection:revalidate'),
  touchBackend: profile => ipcRenderer.invoke('wing:backend:touch', profile),
  getGatewayWsUrl: profile => ipcRenderer.invoke('wing:gateway:ws-url', profile),
  openSessionWindow: (sessionId, opts) => ipcRenderer.invoke('wing:window:openSession', sessionId, opts),
  openNewSessionWindow: () => ipcRenderer.invoke('wing:window:openNewSession'),
  getBootProgress: () => ipcRenderer.invoke('wing:boot-progress:get'),
  getConnectionConfig: profile => ipcRenderer.invoke('wing:connection-config:get', profile),
  saveConnectionConfig: payload => ipcRenderer.invoke('wing:connection-config:save', payload),
  applyConnectionConfig: payload => ipcRenderer.invoke('wing:connection-config:apply', payload),
  testConnectionConfig: payload => ipcRenderer.invoke('wing:connection-config:test', payload),
  probeConnectionConfig: remoteUrl => ipcRenderer.invoke('wing:connection-config:probe', remoteUrl),
  oauthLoginConnectionConfig: remoteUrl => ipcRenderer.invoke('wing:connection-config:oauth-login', remoteUrl),
  oauthLogoutConnectionConfig: remoteUrl => ipcRenderer.invoke('wing:connection-config:oauth-logout', remoteUrl),
  profile: {
    get: () => ipcRenderer.invoke('wing:profile:get'),
    set: name => ipcRenderer.invoke('wing:profile:set', name)
  },
  api: request => ipcRenderer.invoke('wing:api', request),
  notify: payload => ipcRenderer.invoke('wing:notify', payload),
  requestMicrophoneAccess: () => ipcRenderer.invoke('wing:requestMicrophoneAccess'),
  readFileDataUrl: filePath => ipcRenderer.invoke('wing:readFileDataUrl', filePath),
  readFileText: filePath => ipcRenderer.invoke('wing:readFileText', filePath),
  selectPaths: options => ipcRenderer.invoke('wing:selectPaths', options),
  writeClipboard: text => ipcRenderer.invoke('wing:writeClipboard', text),
  saveImageFromUrl: url => ipcRenderer.invoke('wing:saveImageFromUrl', url),
  saveImageBuffer: (data, ext) => ipcRenderer.invoke('wing:saveImageBuffer', { data, ext }),
  saveClipboardImage: () => ipcRenderer.invoke('wing:saveClipboardImage'),
  getPathForFile: file => {
    try {
      return webUtils.getPathForFile(file) || ''
    } catch {
      return ''
    }
  },
  normalizePreviewTarget: (target, baseDir) => ipcRenderer.invoke('wing:normalizePreviewTarget', target, baseDir),
  watchPreviewFile: url => ipcRenderer.invoke('wing:watchPreviewFile', url),
  stopPreviewFileWatch: id => ipcRenderer.invoke('wing:stopPreviewFileWatch', id),
  setTitleBarTheme: payload => ipcRenderer.send('wing:titlebar-theme', payload),
  setNativeTheme: mode => ipcRenderer.send('wing:native-theme', mode),
  setTranslucency: payload => ipcRenderer.send('wing:translucency', payload),
  setPreviewShortcutActive: active => ipcRenderer.send('wing:previewShortcutActive', Boolean(active)),
  openExternal: url => ipcRenderer.invoke('wing:openExternal', url),
  fetchLinkTitle: url => ipcRenderer.invoke('wing:fetchLinkTitle', url),
  sanitizeWorkspaceCwd: cwd => ipcRenderer.invoke('wing:workspace:sanitize', cwd),
  settings: {
    getDefaultProjectDir: () => ipcRenderer.invoke('wing:setting:defaultProjectDir:get'),
    setDefaultProjectDir: dir => ipcRenderer.invoke('wing:setting:defaultProjectDir:set', dir),
    pickDefaultProjectDir: () => ipcRenderer.invoke('wing:setting:defaultProjectDir:pick')
  },
  revealLogs: () => ipcRenderer.invoke('wing:logs:reveal'),
  getRecentLogs: () => ipcRenderer.invoke('wing:logs:recent'),
  readDir: dirPath => ipcRenderer.invoke('wing:fs:readDir', dirPath),
  gitRoot: startPath => ipcRenderer.invoke('wing:fs:gitRoot', startPath),
  worktrees: cwds => ipcRenderer.invoke('wing:fs:worktrees', cwds),
  terminal: {
    dispose: id => ipcRenderer.invoke('wing:terminal:dispose', id),
    resize: (id, size) => ipcRenderer.invoke('wing:terminal:resize', id, size),
    start: options => ipcRenderer.invoke('wing:terminal:start', options),
    write: (id, data) => ipcRenderer.invoke('wing:terminal:write', id, data),
    onData: (id, callback) => {
      const channel = `wing:terminal:${id}:data`
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on(channel, listener)
      return () => ipcRenderer.removeListener(channel, listener)
    },
    onExit: (id, callback) => {
      const channel = `wing:terminal:${id}:exit`
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on(channel, listener)
      return () => ipcRenderer.removeListener(channel, listener)
    }
  },
  onClosePreviewRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('wing:close-preview-requested', listener)
    return () => ipcRenderer.removeListener('wing:close-preview-requested', listener)
  },
  onOpenUpdatesRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('wing:open-updates', listener)
    return () => ipcRenderer.removeListener('wing:open-updates', listener)
  },
  onDeepLink: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('wing:deep-link', listener)
    return () => ipcRenderer.removeListener('wing:deep-link', listener)
  },
  signalDeepLinkReady: () => ipcRenderer.invoke('wing:deep-link-ready'),
  onWindowStateChanged: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('wing:window-state-changed', listener)
    return () => ipcRenderer.removeListener('wing:window-state-changed', listener)
  },
  onFocusSession: callback => {
    const listener = (_event, sessionId) => callback(sessionId)
    ipcRenderer.on('wing:focus-session', listener)
    return () => ipcRenderer.removeListener('wing:focus-session', listener)
  },
  onNotificationAction: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('wing:notification-action', listener)
    return () => ipcRenderer.removeListener('wing:notification-action', listener)
  },
  onPreviewFileChanged: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('wing:preview-file-changed', listener)
    return () => ipcRenderer.removeListener('wing:preview-file-changed', listener)
  },
  onBackendExit: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('wing:backend-exit', listener)
    return () => ipcRenderer.removeListener('wing:backend-exit', listener)
  },
  onPowerResume: callback => {
    const listener = () => callback()
    ipcRenderer.on('wing:power-resume', listener)
    return () => ipcRenderer.removeListener('wing:power-resume', listener)
  },
  onBootProgress: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('wing:boot-progress', listener)
    return () => ipcRenderer.removeListener('wing:boot-progress', listener)
  },
  // First-launch bootstrap progress -- emitted by the install.ps1 stage
  // runner in main.cjs (apps/desktop/electron/bootstrap-runner.cjs).
  // Renderer's install overlay subscribes to live events and queries the
  // current snapshot via getBootstrapState() to recover after a devtools
  // reload mid-bootstrap.
  getBootstrapState: () => ipcRenderer.invoke('wing:bootstrap:get'),
  resetBootstrap: () => ipcRenderer.invoke('wing:bootstrap:reset'),
  repairBootstrap: () => ipcRenderer.invoke('wing:bootstrap:repair'),
  cancelBootstrap: () => ipcRenderer.invoke('wing:bootstrap:cancel'),
  onBootstrapEvent: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('wing:bootstrap:event', listener)
    return () => ipcRenderer.removeListener('wing:bootstrap:event', listener)
  },
  getVersion: () => ipcRenderer.invoke('wing:version'),
  getRemoteDisplayReason: () => ipcRenderer.invoke('wing:get-remote-display-reason'),
  uninstall: {
    summary: () => ipcRenderer.invoke('wing:uninstall:summary'),
    run: mode => ipcRenderer.invoke('wing:uninstall:run', { mode })
  },
  updates: {
    check: () => ipcRenderer.invoke('wing:updates:check'),
    apply: opts => ipcRenderer.invoke('wing:updates:apply', opts),
    getBranch: () => ipcRenderer.invoke('wing:updates:branch:get'),
    setBranch: name => ipcRenderer.invoke('wing:updates:branch:set', name),
    onProgress: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('wing:updates:progress', listener)
      return () => ipcRenderer.removeListener('wing:updates:progress', listener)
    }
  },
  themes: {
    fetchMarketplace: id => ipcRenderer.invoke('wing:vscode-theme:fetch', id),
    searchMarketplace: query => ipcRenderer.invoke('wing:vscode-theme:search', query)
  }
})
