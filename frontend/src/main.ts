// Electron Main Process — ZARA 3.0 Neural Interface
// Renderer is allowed to open independently; Python sidecar connects when ready.

import { app, BrowserWindow, dialog, ipcMain, Notification, shell, type IpcMainInvokeEvent, type MessageBoxOptions } from 'electron'
import { join } from 'path'
import { spawn, ChildProcess } from 'child_process'
import { existsSync } from 'fs'
import { normalizeReminderEvent } from './reminderEvents'

let pythonProcess: ChildProcess | null = null
let mainWindow: BrowserWindow | null = null
let isPythonReady = false
let pythonReadinessPromise: Promise<void> | null = null
let pythonRequestId = 0
const pendingRequests = new Map<string, { resolve: (value: any) => void; reject: (err: Error) => void }>()

function getPythonExecutable(): string {
  if (app.isPackaged) {
    return join(process.resourcesPath, 'backend', 'zara-backend.exe')
  }
  return process.platform === 'win32' ? 'python.exe' : 'python3'
}

function getMainScript(): string {
  if (app.isPackaged) return ''
  // In development app.getAppPath() is the frontend directory.
  return join(app.getAppPath(), '..', 'main.py')
}

function getFrontendDistPath(): string {
  const candidates = [
    join(__dirname, '../dist-frontend'),
    join(app.getAppPath(), 'dist-frontend'),
  ]
  for (const candidate of candidates) {
    if (existsSync(join(candidate, 'index.html'))) {
      console.log('[Electron] Frontend dist:', candidate)
      return candidate
    }
  }
  return candidates[0]
}

function getWindowIconPath(): string {
  if (app.isPackaged) {
    return join(process.resourcesPath, 'assets', 'zara.ico')
  }
  return join(app.getAppPath(), 'public', 'zara.ico')
}

function rejectPendingRequests(reason: string): void {
  for (const [, pending] of pendingRequests) {
    pending.reject(new Error(reason))
  }
  pendingRequests.clear()
}

function startPythonSidecar(): Promise<void> {
  if (pythonProcess && isPythonReady) return Promise.resolve()

  return new Promise((resolve, reject) => {
    let settled = false
    const settleResolve = () => {
      if (settled) return
      settled = true
      resolve()
    }
    const settleReject = (error: Error) => {
      if (settled) return
      settled = true
      reject(error)
    }

    const pythonExe = getPythonExecutable()
    const mainScript = getMainScript()
    isPythonReady = false

    console.log('[Electron] Starting Python sidecar', {
      pythonExe,
      mainScript,
      packaged: app.isPackaged,
      resources: process.resourcesPath,
      appPath: app.getAppPath(),
    })

    if (app.isPackaged && !existsSync(pythonExe)) {
      settleReject(new Error(`Sidecar not found: ${pythonExe}`))
      return
    }
    if (!app.isPackaged && !existsSync(mainScript)) {
      settleReject(new Error(`main.py not found: ${mainScript}`))
      return
    }

    const env = { ...process.env }
    delete env.PYTHONPATH
    env.PYTHONUNBUFFERED = '1'
    env.PYTHONUTF8 = '1'
    env.PYTHONIOENCODING = 'utf-8'

    const args = app.isPackaged ? [] : ['-u', mainScript]
    const child = spawn(pythonExe, args, {
      env,
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true,
    })
    pythonProcess = child

    let stdoutBuffer = ''
    let stderrBuffer = ''

    child.stdout?.on('data', (data) => {
      stdoutBuffer += data.toString()
      const lines = stdoutBuffer.split('\n')
      stdoutBuffer = lines.pop() || ''

      for (const rawLine of lines) {
        const line = rawLine.trim()
        if (!line) continue
        console.log('[Python]', line)

        if (line === 'SYS: Interface neural pronta') {
          isPythonReady = true
          console.log('[Electron] Python sidecar ready')
          settleResolve()
          continue
        }

        try {
          const msg = JSON.parse(line)
          if (msg.request_id && pendingRequests.has(msg.request_id)) {
            const pending = pendingRequests.get(msg.request_id)!
            pendingRequests.delete(msg.request_id)
            if (msg.error) pending.reject(new Error(String(msg.error)))
            else pending.resolve(msg.response ?? msg.result ?? msg)
          } else if (msg.type) {
            handlePythonEvent(msg)
          }
        } catch {
          // Human-readable backend log line, not an IPC frame.
        }
      }
    })

    child.stderr?.on('data', (data) => {
      stderrBuffer += data.toString()
      const lines = stderrBuffer.split('\n')
      stderrBuffer = lines.pop() || ''
      for (const rawLine of lines) {
        const line = rawLine.trim()
        if (line) console.error('[Python ERROR]', line)
      }
    })

    child.on('error', (error) => {
      console.error('[Python] Spawn error:', error)
      if (pythonProcess === child) pythonProcess = null
      isPythonReady = false
      settleReject(error)
    })

    child.on('exit', (code) => {
      console.log('[Python] Exited with code:', code)
      const wasReady = isPythonReady
      if (pythonProcess === child) pythonProcess = null
      isPythonReady = false
      rejectPendingRequests('Python process exited')
      if (!wasReady) {
        settleReject(new Error(`Python sidecar exited before ready (code ${code})`))
      }
    })

    setTimeout(() => {
      if (!isPythonReady) {
        settleReject(new Error('Python sidecar startup timeout (45s)'))
      }
    }, 45000)
  })
}

async function waitForPythonReadiness(): Promise<void> {
  if (pythonProcess && isPythonReady) return

  const readiness = pythonReadinessPromise
  if (!readiness) {
    throw new Error('Python backend startup ainda não foi iniciado')
  }

  // startPythonSidecar rejects after its existing 45-second startup timeout,
  // so boot-time IPC calls cannot accumulate indefinitely.
  await readiness
  if (!pythonProcess || !isPythonReady) {
    throw new Error('Python backend ficou indisponível após a inicialização')
  }
}

async function sendToPython(type: string, payload: any = {}): Promise<any> {
  await waitForPythonReadiness()

  return new Promise((resolve, reject) => {
    if (!pythonProcess || !isPythonReady) {
      reject(new Error('Python backend ainda não está pronto'))
      return
    }

    const requestId = `${Date.now()}-${++pythonRequestId}`
    const message = JSON.stringify({ type, request_id: requestId, payload }) + '\n'
    pendingRequests.set(requestId, { resolve, reject })

    pythonProcess.stdin?.write(message, (error) => {
      if (error) {
        pendingRequests.delete(requestId)
        reject(error)
      }
    })

    // First voice activation may need to download/load the local Vosk model.
    // Keep the UI responsive but allow that explicit user action more time.
    const timeoutMs = type === 'voice-start' ? 300000 : 60000
    setTimeout(() => {
      if (pendingRequests.has(requestId)) {
        pendingRequests.delete(requestId)
        reject(new Error(`Request timeout: ${type}`))
      }
    }, timeoutMs)
  })
}

type JsonRecord = Record<string, unknown>

interface ActionConfirmationChallenge {
  confirmationId: string
  actionFingerprint: string
  expiresAt: string | number
  action: string
  summary: string
}

interface ConfirmationInspection {
  required: boolean
  challenge: ActionConfirmationChallenge | null
}

let actionConfirmationDialogOpen = false

function asRecord(value: unknown): JsonRecord | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? value as JsonRecord
    : null
}

function asNonEmptyString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function inspectConfirmationRequirement(response: unknown): ConfirmationInspection {
  let current: unknown = response
  const visited = new Set<object>()

  for (let depth = 0; depth < 5; depth += 1) {
    const record = asRecord(current)
    if (!record || visited.has(record)) break
    visited.add(record)

    const data = asRecord(record.data)
    const required = record.error === 'CONFIRMATION_REQUIRED' || data?.status === 'CONFIRMATION_REQUIRED'
    if (required) {
      const confirmation = asRecord(data?.confirmation)
      const confirmationId = asNonEmptyString(confirmation?.confirmation_id)
      const actionFingerprint = asNonEmptyString(confirmation?.action_fingerprint)
      const action = asNonEmptyString(confirmation?.action)
      const summary = asNonEmptyString(confirmation?.summary)
      const expiresAt = confirmation?.expires_at
      const validExpiry = (typeof expiresAt === 'string' && Boolean(expiresAt.trim()))
        || (typeof expiresAt === 'number' && Number.isFinite(expiresAt))

      if (confirmationId && actionFingerprint && action && summary && validExpiry) {
        return {
          required: true,
          challenge: { confirmationId, actionFingerprint, expiresAt: expiresAt as string | number, action, summary },
        }
      }
      return { required: true, challenge: null }
    }

    const wrapped = record.response ?? record.result
    if (wrapped === undefined) break
    current = wrapped
  }

  return { required: false, challenge: null }
}

function sanitizeActionParams(params: unknown): JsonRecord | null {
  if (params === undefined || params === null) return {}
  const record = asRecord(params)
  if (!record) return null
  const sanitized = { ...record }
  delete sanitized.confirm
  return sanitized
}

function formatConfirmationExpiry(expiresAt: string | number): string {
  const numeric = typeof expiresAt === 'number' ? expiresAt : Number(expiresAt)
  const milliseconds = Number.isFinite(numeric)
    ? (numeric < 10_000_000_000 ? numeric * 1000 : numeric)
    : Date.parse(String(expiresAt))
  if (!Number.isFinite(milliseconds)) return String(expiresAt)
  return new Date(milliseconds).toLocaleString('pt-BR')
}

function blockedActionResult(error: string, reason: string): JsonRecord {
  return {
    success: false,
    error,
    data: { status: 'BLOCKED', reason },
  }
}

async function cancelActionConfirmation(confirmationId: string): Promise<void> {
  try {
    await sendToPython('action-confirm-cancel', { confirmation_id: confirmationId })
  } catch (error) {
    console.warn('[Electron] Backend did not acknowledge action confirmation cancellation:', error)
  }
}

async function executeActionWithConfirmation(
  event: IpcMainInvokeEvent,
  actionValue: unknown,
  paramsValue: unknown,
): Promise<unknown> {
  const action = asNonEmptyString(actionValue)
  const params = sanitizeActionParams(paramsValue)
  if (!action || !params) {
    return blockedActionResult('INVALID_ACTION_REQUEST', 'INVALID_ACTION_OR_PARAMS')
  }

  const initialResponse = await sendToPython('action-execute', { action, params })
  const inspection = inspectConfirmationRequirement(initialResponse)
  if (!inspection.required) return initialResponse

  // The opaque challenge never crosses back into the renderer process.
  const challenge = inspection.challenge
  if (!challenge) {
    console.error('[Electron] Backend returned a malformed HIGH action confirmation challenge.')
    return blockedActionResult('INVALID_CONFIRMATION_CHALLENGE', 'MALFORMED_BACKEND_CHALLENGE')
  }

  if (challenge.action !== action) {
    console.error('[Electron] HIGH action challenge does not match the requested action.')
    await cancelActionConfirmation(challenge.confirmationId)
    return blockedActionResult('INVALID_CONFIRMATION_CHALLENGE', 'ACTION_MISMATCH')
  }

  if (actionConfirmationDialogOpen) {
    await cancelActionConfirmation(challenge.confirmationId)
    return blockedActionResult('CONFIRMATION_BUSY', 'ANOTHER_CONFIRMATION_IS_OPEN')
  }

  const options: MessageBoxOptions = {
    type: 'warning',
    title: 'ZARA 3.0 — Confirmação de segurança',
    message: `Confirmar ação HIGH: ${challenge.action}`,
    detail: `Resumo: ${challenge.summary}\n\nExpiração: ${formatConfirmationExpiry(challenge.expiresAt)}\n\nA ação só será executada após um clique explícito em “Confirmar ação”.`,
    buttons: ['Cancelar', 'Confirmar ação'],
    defaultId: 0,
    cancelId: 0,
    noLink: true,
  }

  actionConfirmationDialogOpen = true
  let confirmed = false
  try {
    const owner = BrowserWindow.fromWebContents(event.sender)
    const result = owner && !owner.isDestroyed()
      ? await dialog.showMessageBox(owner, options)
      : await dialog.showMessageBox(options)
    confirmed = result.response === 1
  } catch (error) {
    console.error('[Electron] Could not show HIGH action confirmation dialog:', error)
  } finally {
    actionConfirmationDialogOpen = false
  }

  if (!confirmed) {
    await cancelActionConfirmation(challenge.confirmationId)
    return blockedActionResult('CONFIRMATION_CANCELLED', 'USER_CANCELLED')
  }

  try {
    const confirmationResponse = await sendToPython('action-confirm', {
      confirmation_id: challenge.confirmationId,
      action_fingerprint: challenge.actionFingerprint,
      action,
      params,
    })
    if (inspectConfirmationRequirement(confirmationResponse).required) {
      console.error('[Electron] Backend returned another challenge after explicit confirmation.')
      return blockedActionResult('CONFIRMATION_REJECTED', 'BACKEND_DID_NOT_COMPLETE_CONFIRMATION')
    }
    return confirmationResponse
  } catch (error) {
    console.error('[Electron] HIGH action confirmation failed:', error)
    return blockedActionResult('CONFIRMATION_FAILED', 'BACKEND_CONFIRMATION_FAILED')
  }
}

function handlePythonEvent(msg: any): void {
  if (!msg?.type) return
  switch (msg.type) {
    case 'state-change':
      mainWindow?.webContents.send('state-change', msg.state)
      break
    case 'message':
      mainWindow?.webContents.send('message', msg.message)
      break
    case 'metrics':
      mainWindow?.webContents.send('metrics', msg.metrics)
      break
    case 'voice-level':
      mainWindow?.webContents.send('voice-level', msg.level, msg.tone, msg.speaking)
      break
    case 'supercerebro-change':
      mainWindow?.webContents.send('supercerebro-change', msg.active)
      break
    case 'reminder-created':
      mainWindow?.webContents.send('reminder-created', msg.data)
      break
    case 'reminder-fired': {
      const reminder = normalizeReminderEvent(msg.data)
      if (!reminder) {
        console.warn('[Electron] Ignoring malformed reminder-fired event')
        break
      }
      mainWindow?.webContents.send('reminder-fired', reminder)
      const shouldShowNative = !mainWindow || mainWindow.isDestroyed() || !mainWindow.isFocused()
      if (shouldShowNative && Notification.isSupported()) {
        const notification = new Notification({ title: 'Lembrete da ZARA', body: reminder.text })
        notification.on('click', () => {
          if (!mainWindow || mainWindow.isDestroyed()) return
          if (mainWindow.isMinimized()) mainWindow.restore()
          mainWindow.show()
          mainWindow.focus()
        })
        notification.show()
      }
      break
    }
    default:
      console.log('[Electron] Ignoring backend event:', msg.type)
  }
}

function diagnosticHtml(message: string): string {
  const escapes: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }
  const safe = message.replace(/[&<>"']/g, (char) => escapes[char] || char)
  return `<!doctype html><html><body style="margin:0;min-height:100vh;background:#020604;color:#d8ffe9;font-family:Segoe UI,sans-serif;padding:32px;box-sizing:border-box"><h2 style="color:#55ffad">ZARA — falha ao carregar a interface</h2><p>A janela Electron abriu corretamente, porém o renderer não pôde ser carregado.</p><pre style="white-space:pre-wrap;border:1px solid #1a6b4a;padding:16px;border-radius:8px;background:#06100b">${safe}</pre></body></html>`
}

function createWindow(): void {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.focus()
    return
  }

  const iconPath = getWindowIconPath()
  mainWindow = new BrowserWindow({
    width: 1500,
    height: 950,
    minWidth: 1200,
    minHeight: 800,
    frame: false,
    titleBarStyle: 'hidden',
    backgroundColor: '#020604',
    icon: existsSync(iconPath) ? iconPath : undefined,
    show: false,
    webPreferences: {
      preload: join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
    },
  })

  const windowRef = mainWindow
  windowRef.webContents.on('did-fail-load', (_event, errorCode, errorDescription, validatedURL) => {
    console.error('[Renderer] did-fail-load', { errorCode, errorDescription, validatedURL })
  })
  windowRef.webContents.on('render-process-gone', (_event, details) => {
    console.error('[Renderer] render-process-gone', details)
  })
  windowRef.webContents.on('console-message', (_event, level, message, line, sourceId) => {
    if (level >= 2) console.error('[Renderer console]', { level, message, line, sourceId })
  })

  const showWindow = () => {
    if (!windowRef.isDestroyed() && !windowRef.isVisible()) {
      windowRef.show()
      windowRef.focus()
    }
  }
  windowRef.once('ready-to-show', showWindow)
  windowRef.webContents.once('did-finish-load', showWindow)
  setTimeout(showWindow, 3000)

  if (app.isPackaged) {
    const indexPath = join(getFrontendDistPath(), 'index.html')
    windowRef.loadFile(indexPath).catch((error) => {
      console.error('[Renderer] loadFile failed:', error)
      const html = diagnosticHtml(`${error}\n\nindex: ${indexPath}`)
      return windowRef.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(html)}`)
    }).catch((fallbackError) => console.error('[Renderer] diagnostic page failed:', fallbackError))
  } else {
    windowRef.loadURL('http://localhost:5173').catch((error) => {
      console.error('[Renderer] Vite dev server unavailable:', error)
      const html = diagnosticHtml(`Vite dev server indisponível: ${error}`)
      return windowRef.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(html)}`)
    }).catch((fallbackError) => console.error('[Renderer] diagnostic page failed:', fallbackError))
  }

  windowRef.on('closed', () => {
    if (mainWindow === windowRef) mainWindow = null
  })

  windowRef.webContents.setWindowOpenHandler(({ url }) => {
    void shell.openExternal(url)
    return { action: 'deny' }
  })
}

function setupIPC(): void {
  ipcMain.handle('engine-change', (_event, engine: string) => sendToPython('engine-change', { engine }))
  ipcMain.handle('engine-list', () => sendToPython('engine-list'))
  ipcMain.handle('supercerebro-toggle', (_event, active: boolean) => sendToPython('supercerebro-toggle', { active }))
  ipcMain.handle('supercerebro-status', () => sendToPython('supercerebro-status'))
  ipcMain.handle('send-message', (_event, payload) => sendToPython('send-message', payload))
  ipcMain.handle('interrupt', () => sendToPython('interrupt'))
  ipcMain.handle('action-execute', executeActionWithConfirmation)
  ipcMain.handle('action-list', () => sendToPython('action-list'))
  ipcMain.handle('system-metrics', () => sendToPython('system-metrics'))
  ipcMain.handle('system-info', () => sendToPython('system-info'))
  ipcMain.handle('voice-start', () => sendToPython('voice-start'))
  ipcMain.handle('voice-stop', () => sendToPython('voice-stop'))
  ipcMain.handle('voice-status', () => sendToPython('voice-status'))
  ipcMain.handle('config-get', () => sendToPython('config-get'))
  ipcMain.handle('config-set', (_event, key: string, value: any) => sendToPython('config-set', { key, value }))

  // ZARA Lab — council, proposals and approval gate
  ipcMain.handle('lab-state', () => sendToPython('lab-state'))
  ipcMain.handle('lab-send', (_event, payload) => sendToPython('lab-send', payload))
  ipcMain.handle('lab-proposal-create', (_event, payload) => sendToPython('lab-proposal-create', payload))
  ipcMain.handle('lab-proposal-decide', (_event, payload) => sendToPython('lab-proposal-decide', payload))

  // Persistent local reminders
  ipcMain.handle('reminder-create', (_event, payload) => sendToPython('reminder-create', payload))
  ipcMain.handle('reminder-list', (_event, state?: string) => sendToPython('reminder-list', state ? { state } : {}))
  ipcMain.handle('reminder-cancel', (_event, id: string) => sendToPython('reminder-cancel', { id }))

  ipcMain.handle('window-minimize', () => mainWindow?.minimize())
  ipcMain.handle('window-maximize', () => {
    const win = mainWindow
    if (!win) return
    if (win.isMaximized()) win.unmaximize()
    else win.maximize()
  })
  ipcMain.handle('window-close', () => mainWindow?.close())
}

app.whenReady().then(() => {
  // The interface is independent from backend startup. This guarantees that a
  // sidecar failure is visible to the user instead of producing a black window.
  setupIPC()
  pythonReadinessPromise = startPythonSidecar()
  void pythonReadinessPromise.catch((error) => {
    console.error('[Electron] Python backend unavailable:', error)
  })
  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

function stopPython(): void {
  if (pythonProcess) {
    pythonProcess.kill()
    pythonProcess = null
  }
  isPythonReady = false
  pythonReadinessPromise = null
  rejectPendingRequests('Application shutting down')
}

app.on('before-quit', stopPython)
app.on('window-all-closed', () => {
  stopPython()
  if (process.platform !== 'darwin') app.quit()
})

app.on('web-contents-created', (_event, contents) => {
  contents.setWindowOpenHandler(({ url }) => {
    void shell.openExternal(url)
    return { action: 'deny' }
  })
})
