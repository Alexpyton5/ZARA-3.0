// Electron Main Process — ZARA 3.0 Neural Interface
// Renderer is allowed to open independently; Python sidecar connects when ready.

import { app, BrowserWindow, dialog, ipcMain, Notification, shell, type IpcMainInvokeEvent, type MessageBoxOptions } from 'electron'
import { join, isAbsolute } from 'path'
import { spawn, ChildProcess } from 'child_process'
import { existsSync, readdirSync } from 'fs'
import { normalizeReminderEvent } from './reminderEvents'
import { startZoeBridge, type ZoeBridge } from './zoeBridge'
import { createZoeTeamDispatch } from './zoeTeamDispatch'
import { MUSE_CONTEXT_PRESENTATION_SCRIPT, shouldPresentMuseContext } from './museContextPresentation'

let pythonProcess: ChildProcess | null = null
let mainWindow: BrowserWindow | null = null
let isPythonReady = false
let pythonReadinessPromise: Promise<void> | null = null
let pythonRequestId = 0
let zoeBridge: ZoeBridge | null = null
const pendingRequests = new Map<string, { resolve: (value: any) => void; reject: (err: Error) => void }>()

// --- Watchdog do motor (backend) — Frente C, 2026-09-29 ---
// Antes, se o zara-backend.exe morria, o app continuava mudo: todo IPC falhava
// com "ficou indisponível" e nada religava o motor nem avisava o Alex.
// O watchdog respawna com backoff (máx 3 tentativas) e, se não voltar,
// mostra um aviso visível em vez de morrer em silêncio.
type BackendHealth = 'starting' | 'ready' | 'restarting' | 'dead'
let backendHealth: BackendHealth = 'starting'
let backendRestartAttempts = 0
let backendWatchdogRunning = false
let backendDeathNotified = false
let appShuttingDown = false
let zoeBridgeWanted = false
const BACKEND_MAX_RESTARTS = 3
const BACKEND_RESTART_BACKOFF_MS = [2000, 5000, 15000]

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function getPythonExecutable(): string {
  if (app.isPackaged) {
    return join(process.resourcesPath, 'backend', 'zara-backend.exe')
  }
  if (process.env.ZARA_DEV_PYTHON) return process.env.ZARA_DEV_PYTHON
  const localVenv = join(__dirname, '..', '..', '.venv', 'Scripts', 'python.exe')
  if (process.platform === 'win32' && existsSync(localVenv)) return localVenv
  return process.platform === 'win32' ? 'python.exe' : 'python3'
}

function getMainScript(): string {
  if (app.isPackaged) return ''
  // __dirname is frontend/dist-electron in development.
  return join(__dirname, '..', '..', 'main.py')
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
    return join(process.resourcesPath, 'assets', 'tropa-dev.ico')
  }
  return join(app.getAppPath(), 'public', 'tropa-dev.ico')
}

function rejectPendingRequests(reason: string): void {
  for (const [, pending] of pendingRequests) {
    pending.reject(new Error(reason))
  }
  pendingRequests.clear()
}

// Canal 'backend-status' para a interface (a Frente B liga o banner da UI aqui):
// { status: 'starting' | 'ready' | 'restarting' | 'dead', detail: string | null, attempts: number }
function broadcastBackendStatus(status: BackendHealth, detail?: string): void {
  backendHealth = status
  try {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('backend-status', {
        status,
        detail: detail ?? null,
        attempts: backendRestartAttempts,
      })
    }
  } catch (error) {
    console.error('[Electron] Falha ao avisar a interface sobre o backend:', error)
  }
}

function noteBackendReady(): void {
  backendRestartAttempts = 0
  backendDeathNotified = false
  broadcastBackendStatus('ready')
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
        if (line === 'SYS: Interface neural pronta') {
          console.log('[Python]', line)
          isPythonReady = true
          console.log('[Electron] Python sidecar ready')
          noteBackendReady()
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
          console.log('[Python]', line)
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
      const isCurrent = pythonProcess === child
      if (isCurrent) {
        pythonProcess = null
        isPythonReady = false
      }
      settleReject(error)
      // Watchdog: falha de spawn também tenta religar o motor.
      if (isCurrent && !appShuttingDown) {
        void runBackendWatchdog(false, `falha ao iniciar: ${error.message}`)
      }
    })

    child.on('exit', (code, signal) => {
      console.log('[Python] Exited with code:', code, 'signal:', signal)
      const wasReady = isPythonReady
      const isCurrent = pythonProcess === child
      if (isCurrent) {
        pythonProcess = null
        isPythonReady = false
        rejectPendingRequests('Python process exited')
      }
      if (!wasReady) {
        settleReject(new Error(`Python sidecar exited before ready (code ${code})`))
      }
      // Watchdog (Frente C): morte fora do desligamento tenta religar o motor
      // sozinho, com backoff — antes o app simplesmente continuava mudo.
      if (isCurrent && !appShuttingDown) {
        void runBackendWatchdog(wasReady, `exit code=${code}${signal ? `, sinal=${signal}` : ''}`)
      }
    })

    setTimeout(() => {
      if (!isPythonReady) {
        settleReject(new Error('Python sidecar startup timeout (45s)'))
        if (!appShuttingDown && pythonProcess === child) {
          console.error('[Electron] Backend não ficou pronto em 45s — encerrando para o watchdog religar')
          try {
            child.kill()
          } catch {
            // O processo já morreu por conta própria; o 'exit' resolve.
          }
        }
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
  try {
    await readiness
  } catch (error) {
    // Boot lento: o timeout estourou mas o backend ficou pronto mesmo assim.
    if (pythonProcess && isPythonReady) return
    throw error
  }
  if (!pythonProcess || !isPythonReady) {
    throw new Error('Python backend ficou indisponível após a inicialização')
  }
}

async function sendToPython(type: string, payload: any = {}, requestIdOverride?: string): Promise<any> {
  await waitForPythonReadiness()

  return new Promise((resolve, reject) => {
    if (!pythonProcess || !isPythonReady) {
      reject(new Error('Python backend ainda não está pronto'))
      return
    }

    const requestId = requestIdOverride || `${Date.now()}-${++pythonRequestId}`
    if (pendingRequests.has(requestId)) {
      reject(new Error(`Request already pending: ${requestId}`))
      return
    }
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
    // The desktop agent may use its full 120-second observe/act/verify loop.
    const timeoutMs = type === 'voice-start' ? 300000 : type === 'zoe-remote-command' ? 190000 : ['computer-agent-run', 'pilot-command'].includes(type) ? 135000 : 60000
    setTimeout(() => {
      if (pendingRequests.has(requestId)) {
        pendingRequests.delete(requestId)
        reject(new Error(`Request timeout: ${type}`))
      }
    }, timeoutMs)
  })
}

// Religar o motor automaticamente quando ele morre (exit/close do processo).
// Backoff entre tentativas; após BACKEND_MAX_RESTARTS falhas, aviso visível.
async function runBackendWatchdog(wasReady: boolean, deathInfo: string): Promise<void> {
  if (backendWatchdogRunning) return
  backendWatchdogRunning = true
  try {
    // A ponte falava com o backend morto: fecha para recriar após o religamento.
    if (zoeBridge) {
      const staleBridge = zoeBridge
      zoeBridge = null
      try {
        await staleBridge.close()
      } catch (error) {
        console.error('[Electron] Erro ao fechar ponte do backend morto:', error)
      }
    }
    while (!appShuttingDown && backendRestartAttempts < BACKEND_MAX_RESTARTS) {
      const waitMs = BACKEND_RESTART_BACKOFF_MS[Math.min(backendRestartAttempts, BACKEND_RESTART_BACKOFF_MS.length - 1)]
      backendRestartAttempts += 1
      console.log(`[Electron] Watchdog do backend: tentativa ${backendRestartAttempts}/${BACKEND_MAX_RESTARTS} em ${waitMs}ms (morte: ${deathInfo})`)
      broadcastBackendStatus('restarting', `Tentativa ${backendRestartAttempts} de ${BACKEND_MAX_RESTARTS} para religar o motor…`)
      await sleep(waitMs)
      if (appShuttingDown) break
      // Outra frente (ex.: religamento manual) já resolveu: não duplicar.
      if (pythonProcess && isPythonReady) {
        noteBackendReady()
        return
      }
      try {
        pythonReadinessPromise = startPythonSidecar()
        await pythonReadinessPromise
        noteBackendReady()
        console.log('[Electron] Watchdog do backend: motor religado com sucesso')
        await restartZoeBridgeIfWanted()
        return
      } catch (error) {
        console.error(`[Electron] Watchdog do backend: tentativa ${backendRestartAttempts} falhou:`, error)
      }
    }
    if (!appShuttingDown && !isPythonReady) {
      const detail = wasReady
        ? 'O motor da ZARA (backend) parou de funcionar.'
        : 'O motor da ZARA (backend) não conseguiu iniciar.'
      await showBackendDeadWarning(
        `${detail} Tentamos religar ${backendRestartAttempts} vezes sem sucesso.`,
      )
    }
  } finally {
    backendWatchdogRunning = false
  }
}

// Aviso visível (nativo) quando o motor não volta: antes isso era silêncio total.
// A interface também recebe o evento 'backend-status' p/ mostrar banner próprio.
async function showBackendDeadWarning(detail: string): Promise<void> {
  if (backendDeathNotified) return
  backendDeathNotified = true
  broadcastBackendStatus('dead', detail)
  // Disposable package smoke runs must stay invisible and must never invite
  // a relaunch into the owner's desktop when an isolated backend fails.
  if (process.env.ZARA_SMOKE_TEST === '1') return
  try {
    if (mainWindow && !mainWindow.isDestroyed()) {
      if (mainWindow.isMinimized()) mainWindow.restore()
      mainWindow.show()
    }
  } catch {
    // Melhor esforço: o diálogo abaixo já é visível por si só.
  }
  const options: MessageBoxOptions = {
    type: 'warning',
    title: 'TROPA dev. — motor parado',
    message: 'O motor da TROPA dev. parou.',
    detail: `${detail}\n\nVoz e controle do PC estão indisponíveis até o motor voltar.`,
    buttons: ['Reiniciar agora', 'Continuar sem motor'],
    defaultId: 0,
    cancelId: 1,
    noLink: true,
  }
  try {
    const owner = mainWindow && !mainWindow.isDestroyed() ? mainWindow : undefined
    const result = owner
      ? await dialog.showMessageBox(owner, options)
      : await dialog.showMessageBox(options)
    if (result.response === 0) {
      app.relaunch()
      app.exit(0)
    }
  } catch (error) {
    console.error('[Electron] Não foi possível exibir o aviso de motor parado:', error)
  }
}

// Religamento manual (a interface pode expor num botão "tentar de novo").
async function retryBackendNow(): Promise<{ ok: boolean; status: BackendHealth }> {
  if (pythonProcess && isPythonReady) return { ok: true, status: backendHealth }
  if (backendWatchdogRunning) return { ok: false, status: backendHealth }
  backendRestartAttempts = 0
  backendDeathNotified = false
  await runBackendWatchdog(false, 'religamento manual')
  return { ok: pythonProcess !== null && isPythonReady, status: backendHealth }
}

async function startZoeBridgeOnce(): Promise<void> {
  if (zoeBridge || !isPythonReady) return
  const base = process.env.ZARA3_HOME || join(process.env.LOCALAPPDATA || app.getPath('userData'), 'ZARA3')
  zoeBridge = await startZoeBridge(
    join(base, 'zoe_bridge'), createZoeTeamDispatch(sendToPython, sendDurableLabOperation),
  )
  zoeBridgeWanted = true
  console.log('[Zoe Bridge] Local bridge ready')
}

async function restartZoeBridgeIfWanted(): Promise<void> {
  if (!zoeBridgeWanted || zoeBridge || !isPythonReady) return
  try {
    await startZoeBridgeOnce()
  } catch (error) {
    console.error('[Zoe Bridge] Unavailable after backend restart:', error)
  }
}

type DurableLabCommand = 'lab.v1.submit' | 'lab.v1.message' | 'lab.v1.room' | 'lab.v1.cancel'

async function sendDurableLabOperation(
  command: DurableLabCommand,
  payload: Record<string, unknown>,
  requestIdValue?: unknown,
): Promise<any> {
  const requestId = typeof requestIdValue === 'string' ? requestIdValue.trim() : ''
  if (!/^[A-Za-z0-9_.:-]{1,120}$/.test(requestId)) {
    return {
      success: false,
      accepted: false,
      state: 'REJECTED',
      code: 'INVALID_OPERATION',
      error: 'Identificador da operação do Lab inválido.',
    }
  }

  const admission = await sendToPython(
    'lab-v1-admit-operation', { command, payload }, requestId,
  )
  if (admission?.success !== true || admission?.accepted !== true
      || typeof admission.operation_id !== 'string' || !admission.operation_id) {
    return admission
  }

  const confirmation = await sendToPython(
    'lab-v1-confirm-operation',
    { operation_id: admission.operation_id },
    `${requestId}:confirm`,
  )
  if (confirmation?.confirmed !== true
      || confirmation.operation_id !== admission.operation_id) {
    return { ...admission, ...confirmation, accepted: true, success: false }
  }

  return {
    ...admission,
    ...confirmation,
    request_id: admission.request_id,
    operation_id: admission.operation_id,
    command: admission.command,
    payload_sha256: admission.payload_sha256,
    accepted_at: admission.accepted_at,
    accepted: true,
    success: true,
  }
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
    title: 'TROPA dev. — Confirmação de segurança',
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
    case 'voice-output-audio':
      mainWindow?.webContents.send('voice-output-audio', msg.data)
      break
    case 'zoe-voice-input':
      mainWindow?.webContents.send('zoe-voice-input', msg.data)
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
    case 'computer_agent_started': {
      const data = (msg.data ?? {}) as { goal?: unknown }
      showComputerAgentOverlay()
      const payload = { goal: typeof data.goal === 'string' ? data.goal : '' }
      sendToComputerAgentOverlay('computer-agent-started', payload)
      mainWindow?.webContents.send('computer-agent-started', payload)
      break
    }
    case 'computer_agent_step': {
      const data = (msg.data ?? {}) as { step?: unknown; index?: unknown; total?: unknown }
      const payload = {
        step: typeof data.step === 'string' ? data.step : '',
        index: typeof data.index === 'number' ? data.index : undefined,
        total: typeof data.total === 'number' ? data.total : undefined,
      }
      sendToComputerAgentOverlay('computer-agent-step', payload)
      mainWindow?.webContents.send('computer-agent-step', payload)
      break
    }
    case 'computer_agent_stopped': {
      const data = (msg.data ?? {}) as {
        goal?: unknown
        success?: unknown
        refused?: unknown
        verified?: unknown
        steps?: unknown
        error?: unknown
      }
      const payload = {
        goal: typeof data.goal === 'string' ? data.goal : '',
        success: data.success === true,
        refused: data.refused === true,
        verified: data.verified === true,
        steps: typeof data.steps === 'number' ? data.steps : 0,
        error: typeof data.error === 'string' ? data.error : null,
      }
      sendToComputerAgentOverlay('computer-agent-stopped', payload)
      mainWindow?.webContents.send('computer-agent-stopped', payload)
      hideComputerAgentOverlay()
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

// Home shortcuts accept semantic IDs only. Renderer text never becomes a
// command, arbitrary path or URL.
type DesktopResult = { success: boolean; output?: string; error?: string }
const desktopLinks: Record<string, string> = {
  whatsapp: 'https://web.whatsapp.com/',
  telegram: 'https://web.telegram.org/',
  instagram: 'https://www.instagram.com/',
  gmail: 'https://mail.google.com/',
  figma: 'https://www.figma.com/',
}
const desktopSettings: Record<string, string> = {
  storage: 'ms-settings:storagesense', temporary: 'ms-settings:storagesense',
  startup: 'ms-settings:startupapps', update: 'ms-settings:windowsupdate',
  security: 'windowsdefender:', firewall: 'windowsdefender://network',
  privacy: 'ms-settings:privacy', power: 'ms-settings:powersleep',
}

async function openDesktopLink(targets: Record<string, string>, id: unknown): Promise<DesktopResult> {
  const target = typeof id === 'string' && Object.hasOwn(targets, id) ? targets[id] : null
  if (!target) return { success: false, error: 'Destino não reconhecido.' }
  try {
    await shell.openExternal(target)
    return { success: true, output: 'Solicitação de abertura enviada ao Windows.' }
  } catch (error) {
    return { success: false, error: error instanceof Error ? error.message : 'Não foi possível abrir o destino.' }
  }
}

function resolveDesktopApp(id: unknown): string | null {
  if (typeof id !== 'string' || !['vscode', 'figma', 'postman', 'docker'].includes(id)) return null
  const local = process.env.LOCALAPPDATA || join(app.getPath('home'), 'AppData', 'Local')
  const programs = process.env.ProgramFiles || 'C:\\Program Files'
  const candidates: Record<string, string[]> = {
    vscode: [join(local, 'Programs', 'Microsoft VS Code', 'Code.exe'), join(programs, 'Microsoft VS Code', 'Code.exe')],
    figma: [join(local, 'Figma', 'Figma.exe')],
    postman: [join(local, 'Postman', 'Postman.exe'), join(programs, 'Postman', 'Postman.exe')],
    docker: [join(programs, 'Docker', 'Docker', 'Docker Desktop.exe')],
  }
  if (id === 'figma' || id === 'postman') {
    const name = id === 'figma' ? 'Figma' : 'Postman'
    const directory = join(local, name)
    try {
      const versions = readdirSync(directory, { withFileTypes: true })
        .filter(entry => entry.isDirectory() && /^app-\d[\d.]*$/.test(entry.name))
        .map(entry => entry.name).sort((a, b) => b.localeCompare(a, undefined, { numeric: true }))
      for (const version of versions) candidates[id].push(join(directory, version, `${name}.exe`))
    } catch { /* instalação ausente é um estado normal. */ }
  }
  return candidates[id].find(candidate => existsSync(candidate)) || null
}

async function openDesktopPath(path: string | null): Promise<DesktopResult> {
  if (!path) return { success: false, error: 'Aplicativo não encontrado neste computador.' }
  try {
    const error = await shell.openPath(path)
    return error ? { success: false, error } : { success: true, output: 'Solicitação de abertura enviada ao Windows.' }
  } catch (error) {
    return { success: false, error: error instanceof Error ? error.message : 'Não foi possível abrir o destino.' }
  }
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
      webviewTag: true, // Aba "ZOE": permite <webview> para embutir o app da zoe
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
    if (message.startsWith('[VOICE_TRACE]')) console.info(message)
    if (level >= 2) console.error('[Renderer console]', { level, message, line, sourceId })
  })

  const showWindow = () => {
    if (process.argv.includes('--minimizada')) return
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

// --- Overlay do computer-agent (use-computer) — contrato Frente B, 29/09 ---
// Janela fullscreen transparente, click-through, que mostra a borda neon
// enquanto o backend usa o PC. O renderer a usa via ?overlay=computer-agent.
let computerAgentOverlay: BrowserWindow | null = null

function createComputerAgentOverlay(): BrowserWindow {
  if (computerAgentOverlay && !computerAgentOverlay.isDestroyed()) return computerAgentOverlay
  const overlay = new BrowserWindow({
    fullscreen: true,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    skipTaskbar: true, // não aparece na barra de tarefas
    focusable: false, // nunca rouba o foco
    resizable: false,
    movable: false,
    minimizable: false,
    maximizable: false,
    show: false,
    webPreferences: {
      preload: join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })
  overlay.setIgnoreMouseEvents(true) // click-through: o mouse atravessa
  overlay.setAlwaysOnTop(true, 'screen-saver')
  if (app.isPackaged) {
    // loadFile aceita query: a URL final é index.html?overlay=computer-agent
    overlay.loadFile(join(getFrontendDistPath(), 'index.html'), { query: { overlay: 'computer-agent' } })
  } else {
    overlay.loadURL('http://localhost:5173?overlay=computer-agent')
  }
  overlay.on('closed', () => {
    if (computerAgentOverlay === overlay) computerAgentOverlay = null
  })
  computerAgentOverlay = overlay
  return overlay
}

function showComputerAgentOverlay(): void {
  const overlay = createComputerAgentOverlay()
  if (!overlay.isDestroyed() && !overlay.isVisible()) overlay.showInactive() // mostra sem roubar o foco
}

// Envia para o overlay mesmo que ele ainda esteja carregando: webContents.send
// numa página em load é descartado em silêncio — sem este helper a borda neon
// nunca acenderia no primeiro uso (janela recém-criada ainda carregando).
function sendToComputerAgentOverlay(
  channel: 'computer-agent-started' | 'computer-agent-step' | 'computer-agent-stopped',
  payload: unknown,
): void {
  const overlay = computerAgentOverlay
  if (!overlay || overlay.isDestroyed()) return
  if (overlay.webContents.isLoading()) {
    overlay.webContents.once('did-finish-load', () => {
      if (!overlay.isDestroyed()) overlay.webContents.send(channel, payload)
    })
  } else {
    overlay.webContents.send(channel, payload)
  }
}

function hideComputerAgentOverlay(): void {
  if (computerAgentOverlay && !computerAgentOverlay.isDestroyed()) {
    computerAgentOverlay.close() // destrói; recria no próximo start
    computerAgentOverlay = null
  }
}

function setupIPC(): void {
  ipcMain.handle('pilot-context', (_event, payload) => sendToPython('pilot-context', payload))
  ipcMain.handle('pilot-command', (_event, payload) => sendToPython('pilot-command', payload))
  ipcMain.handle('nova-ui-state', () => sendToPython('nova-ui-state'))
  ipcMain.handle('nova-ui-pause', () => sendToPython('nova-ui-pause'))
  ipcMain.handle('nova-ui-resume', () => sendToPython('nova-ui-resume'))
  ipcMain.handle('nova-ui-decision', async (_event, payload) => {
    const result = await sendToPython('nova-ui-decision', payload)
    if (result?.success !== true || result?.accepted !== true || typeof result.operation_id !== 'string') return result
    const confirmation = await sendToPython('lab-v1-confirm-operation', { operation_id: result.operation_id })
    if (confirmation?.confirmed !== true || confirmation.operation_id !== result.operation_id) {
      return { ...result, success: false, error: confirmation?.error || 'O motor não confirmou essa decisão.' }
    }
    return { ...result, ...confirmation, success: true }
  })
  ipcMain.handle('nova-ui-open-result', async (_event, target: unknown) => {
    if (typeof target !== 'string' || !target.trim()) return { success: false, error: 'O resultado não tem um endereço válido.' }
    try {
      if (/^https?:\/\//i.test(target)) {
        await shell.openExternal(new URL(target).href)
      } else {
        if (!isAbsolute(target) || !existsSync(target)) return { success: false, error: 'O arquivo do resultado não foi encontrado.' }
        const error = await shell.openPath(target)
        if (error) return { success: false, error }
      }
      return { success: true }
    } catch { return { success: false, error: 'Não consegui abrir esse resultado.' } }
  })
  ipcMain.handle('zoe-bridge-status', () => ({ ready: Boolean(zoeBridge && isPythonReady) }))
  ipcMain.handle('engine-change', (_event, engine: string) => sendToPython('engine-change', { engine }))
  ipcMain.handle('engine-list', () => sendToPython('engine-list'))
  ipcMain.handle('supercerebro-toggle', (_event, active: boolean) => sendToPython('supercerebro-toggle', { active }))
  ipcMain.handle('supercerebro-status', () => sendToPython('supercerebro-status'))
  ipcMain.handle('send-message', (_event, payload) => sendToPython('send-message', payload))
  ipcMain.handle('interrupt', () => sendToPython('interrupt'))
  ipcMain.handle('voice-mute', (_event, mudo?: boolean) => sendToPython('voice-mute', { mudo }))
  ipcMain.on('voice-mic-chunk', (_event, pcm: string) => {
    if (!pythonProcess || !isPythonReady || !pcm) return
    try {
      pythonProcess.stdin?.write(JSON.stringify({ type: 'voice-mic-chunk', payload: { pcm } }) + '\n')
    } catch {
      // O próximo bloco de áudio tentará novamente se o backend estiver caindo.
    }
  })
  ipcMain.handle('conversation-history-list', (_event, payload) => sendToPython('conversation-history-list', payload))
  ipcMain.handle('conversation-history-clear', () => sendToPython('conversation-history-clear'))
  ipcMain.handle('memory-galaxy-list', () => sendToPython('memory-galaxy-list'))
  ipcMain.handle('memory-user-add', (_event, payload) => sendToPython('memory-user-add', payload))
  ipcMain.handle('memory-user-search', (_event, payload) => sendToPython('memory-user-search', payload))
  ipcMain.handle('memory-user-list', (_event, payload) => sendToPython('memory-user-list', payload))
  ipcMain.handle('memory-user-forget', (_event, payload) => sendToPython('memory-user-forget', payload))
  ipcMain.handle('project-memory-get', (_event, payload) => sendToPython('project-memory-get', payload))
  ipcMain.handle('project-memory-list', () => sendToPython('project-memory-list'))
  ipcMain.handle('project-memory-context', () => sendToPython('project-memory-context'))
  ipcMain.handle('action-execute', executeActionWithConfirmation)
  ipcMain.handle('action-list', () => sendToPython('action-list'))
  ipcMain.handle('system-metrics', () => sendToPython('system-metrics'))
  ipcMain.handle('self-status', () => sendToPython('self-status'))
  ipcMain.handle('system-info', () => sendToPython('system-info'))
  ipcMain.handle('voice-start', () => sendToPython('voice-start'))
  ipcMain.handle('zoe-voice-start', () => sendToPython('voice-start', { target: 'zoe' }))
  ipcMain.handle('zoe-voice-speak', (_event, text: string) => sendToPython('zoe-voice-speak', { text }))
  ipcMain.handle('voice-stop', () => sendToPython('voice-stop'))
  ipcMain.handle('voice-status', () => sendToPython('voice-status'))
  ipcMain.handle('voice-engine-get', () => sendToPython('voice-engine-get'))
  ipcMain.handle('voice-engine-set', (_event, payload) => sendToPython('voice-engine-set', payload))
  ipcMain.handle('config-get', () => sendToPython('config-get'))
  ipcMain.handle('config-set', (_event, key: string, value: any) => sendToPython('config-set', { key, value }))

  // ZARA Lab — council, proposals and approval gate
  ipcMain.handle('lab-state', () => sendToPython('lab-state'))
  ipcMain.handle('lab-send', (_event, payload) => sendToPython('lab-send', payload))
  ipcMain.handle('lab-proposal-create', (_event, payload) => sendToPython('lab-proposal-create', payload))
  ipcMain.handle('lab-proposal-decide', (_event, payload) => sendToPython('lab-proposal-decide', payload))

  // Living Team mission and autonomous mode.
  ipcMain.handle('lab-mission-state', () => sendToPython('lab-mission-state'))
  ipcMain.handle('lab-mission-verify', (_event, payload) => sendToPython('lab-mission-verify', payload))
  ipcMain.handle('lab-mission-cycle', (_event, payload) => sendToPython('lab-mission-cycle', payload))
  ipcMain.handle('lab-mission-recruit', (_event, payload) => sendToPython('lab-mission-recruit', payload))
  ipcMain.handle('lab-mission-finding', (_event, payload) => sendToPython('lab-mission-finding', payload))
  ipcMain.handle('lab-mission-prioritize', (_event, payload) => sendToPython('lab-mission-prioritize', payload))
  ipcMain.handle('lab-mission-patch', (_event, payload) => sendToPython('lab-mission-patch', payload))
  ipcMain.handle('lab-mission-bot', (_event, payload) => sendToPython('lab-mission-bot', payload))
  ipcMain.handle('lab-autonomy-start', (_event, payload) => sendToPython('lab-autonomy-start', payload || {}))
  ipcMain.handle('lab-autonomy-stop', () => sendToPython('lab-autonomy-stop'))
  ipcMain.handle('lab-autonomy-status', () => sendToPython('lab-autonomy-status'))

  // ZARA Lab V1 — todos os canais expostos pela ponte preload.
  ipcMain.handle('lab-v1-room-message', (_event, payload) => sendDurableLabOperation(
    'lab.v1.room', { session_id: payload?.session_id, content: payload?.content }, payload?.request_id,
  ))
  ipcMain.handle('lab-v1-snapshot', (_event, payload) => sendToPython('lab-v1-snapshot', payload))
  ipcMain.handle('lab-v1-proposal-list', (_event, payload) => sendToPython('lab-v1-proposal-list', payload))
  ipcMain.handle('lab-v1-proposal-update', (_event, payload) => sendToPython('lab-v1-proposal-update', payload))
  ipcMain.handle('lab-v1-create-session', (_event, payload) => sendToPython('lab-v1-create-session', payload))
  ipcMain.handle('lab-v1-submit', (_event, payload) => sendDurableLabOperation(
    'lab.v1.message', { session_id: payload?.session_id, content: payload?.text }, payload?.request_id,
  ))
  ipcMain.handle('lab-v1-autopilot', (_event, payload) => sendDurableLabOperation(
    'lab.v1.submit', { objective: payload?.intent }, payload?.request_id,
  ))
  ipcMain.handle('lab-v1-autopilot-activate', (_event, payload) => sendToPython('lab-v1-autopilot-activate', payload))
  ipcMain.handle('lab-v1-autonomy-configure', (_event, payload) => sendToPython('lab-v1-autonomy-configure', payload))
  ipcMain.handle('lab-v1-cancel-mission', (_event, payload) => sendDurableLabOperation(
    'lab.v1.cancel', { session_id: payload?.session_id }, payload?.request_id,
  ))
  ipcMain.handle('lab-v1-delete-session', (_event, payload) => sendToPython('lab-v1-delete-session', payload))
  ipcMain.handle('lab-v1-providers', () => sendToPython('lab-v1-providers'))
  ipcMain.handle('lab-v1-create-agent', (_event, payload) => sendToPython('lab-v1-create-agent', payload))
  ipcMain.handle('lab-v1-configure-agent', (_event, payload) => sendToPython('lab-v1-configure-agent', payload))
  ipcMain.handle('lab-v1-agent-profiles', (_event, payload) => sendToPython('lab-v1-agent-profiles', payload))
  ipcMain.handle('lab-v1-agent-profile-update', (_event, payload) => sendToPython('lab-v1-agent-profile-update', payload))
  ipcMain.handle('lab-v1-agent-profile-rollback', (_event, payload) => sendToPython('lab-v1-agent-profile-rollback', payload))
  ipcMain.handle('lab-v1-archive-agent', (_event, payload) => sendToPython('lab-v1-archive-agent', payload))
  ipcMain.handle('lab-v1-rebind-role', (_event, payload) => sendToPython('lab-v1-rebind-role', payload))
  ipcMain.handle('lab-v1-research-skill', (_event, payload) => sendToPython('lab-v1-research-skill', payload))
  ipcMain.handle('lab-v1-team-chat', (_event, payload) => sendToPython('lab-v1-team-chat', payload))

  // Conselheira — chat com a zoe via ponte Gmail
  ipcMain.handle('conselheira-send', (_event, payload) => sendToPython('conselheira-send', payload))
  ipcMain.handle('conselheira-sync', () => sendToPython('conselheira-sync'))
  ipcMain.handle('conselheira-messages', (_event, payload) => sendToPython('conselheira-messages', payload))
  ipcMain.handle('conselheira-status', () => sendToPython('conselheira-status'))

  // Persistent local reminders
  ipcMain.handle('reminder-create', (_event, payload) => sendToPython('reminder-create', payload))
  ipcMain.handle('reminder-list', (_event, state?: string) => sendToPython('reminder-list', state ? { state } : {}))
  ipcMain.handle('reminder-cancel', (_event, id: string) => sendToPython('reminder-cancel', { id }))

  ipcMain.handle('desktop-open-app', (_event, id: unknown) => openDesktopPath(resolveDesktopApp(id)))
  ipcMain.handle('desktop-open-external', (_event, id: unknown) => openDesktopLink(desktopLinks, id))
  ipcMain.handle('desktop-open-settings', (_event, id: unknown) => openDesktopLink(desktopSettings, id))
  ipcMain.handle('desktop-open-folder', (_event, id: unknown) => {
    if (id !== 'home' && id !== 'documents' && id !== 'downloads' && id !== 'desktop') {
      return { success: false, error: 'Pasta não reconhecida.' }
    }
    return openDesktopPath(app.getPath(id))
  })

  ipcMain.handle('backend-retry', () => retryBackendNow())
  ipcMain.handle('backend-health', () => ({
    status: backendHealth,
    attempts: backendRestartAttempts,
    ready: isPythonReady,
  }))
  // Computer-agent (use-computer) — contrato Frente B
  ipcMain.handle('computer-agent-run', (_event, payload) => sendToPython('computer-agent-run', payload))
  ipcMain.handle('computer-agent-overlay-show', () => {
    showComputerAgentOverlay()
    return { ok: true }
  })
  ipcMain.handle('computer-agent-overlay-hide', () => {
    hideComputerAgentOverlay()
    return { ok: true }
  })
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
  void pythonReadinessPromise.then(() => startZoeBridgeOnce()).catch((error) => console.error('[Zoe Bridge] Unavailable:', error))
  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

function stopPython(): void {
  appShuttingDown = true
  const bridge = zoeBridge
  zoeBridge = null
  if (bridge) void bridge.close()
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
  contents.on('dom-ready', () => {
    if (!shouldPresentMuseContext(contents.getType(), contents.getURL())) return
    void contents.executeJavaScript(MUSE_CONTEXT_PRESENTATION_SCRIPT)
      .catch(() => console.warn('[Muse] Message presentation unavailable'))
  })
  contents.setWindowOpenHandler(({ url }) => {
    void shell.openExternal(url)
    return { action: 'deny' }
  })
})
