// Electron Main Process — ZARA 3.0 Neural Interface
// Renderer is allowed to open independently; Python sidecar connects when ready.

import { app, BrowserWindow, dialog, ipcMain, Menu, Notification, session, shell, Tray, type IpcMainInvokeEvent, type MessageBoxOptions } from 'electron'
import { join } from 'path'
import { spawn, execFile, execFileSync, ChildProcess } from 'child_process'
import { existsSync, mkdirSync, writeFileSync, readFileSync, renameSync, unlinkSync } from 'fs'
import { createHash } from 'crypto'
import { normalizeReminderEvent } from './reminderEvents'

let pythonProcess: ChildProcess | null = null
let mainWindow: BrowserWindow | null = null
let isPythonReady = false
let pythonReadinessPromise: Promise<void> | null = null
let isStoppingPython = false
// ZARA-SIDECAR-ORFAO-001: guardado à parte porque em `will-quit` o objeto do
// processo já pode ter sido descartado, e ainda assim precisamos do pid.
let lastPythonPid: number | undefined
let pythonRequestId = 0
const pendingRequests = new Map<string, { resolve: (value: any) => void; reject: (err: Error) => void }>()

// ZARA-BANDEJA-001
//
// A ZARA permanece disponível na bandeja quando a janela é fechada.
// O sidecar mantém voz, lembretes e automações locais enquanto a janela está oculta.
// Fechar a janela não encerra o aplicativo; sair de verdade usa o menu da bandeja.

//
// Fechar a janela passa a ESCONDER a janela, não a encerrar a ZARA. O X vira
// "some da minha frente", e sair de verdade fica no menu da bandeja. Assim o
// A ZARA funciona em segundo plano sem manter a janela aberta.
//
// Isto NÃO enfraquece a proteção contra sidecar órfão: `saindoDeVerdade` só
// fica verdadeiro no caminho de saída explícito, e aí `before-quit` e
// `will-quit` continuam matando a árvore de processos como antes.
let tray: Tray | null = null
let saindoDeVerdade = false
const abriuMinimizada = process.argv.includes('--minimizada')

function getPythonExecutable(): string {
  if (app.isPackaged) {
    return join(process.resourcesPath, 'backend', 'zara-backend.exe')
  }
  // BUGFIX_2026-09-03: bare "python.exe" resolves via PATH, which has
  // pointed at a DIFFERENT project's venv before (documented incident,
  // see .claude/rules/path-rules/backend-core.md) and did again here —
  // the sidecar exited immediately with "Missing essential dependencies:
  // pydantic_settings" because PATH python isn't this project's venv.
  // Always use the project's own venv by explicit path in dev.
  const devVenvPython = join(app.getAppPath(), '..', '..', '.venv', 'Scripts', 'python.exe')
  if (process.platform === 'win32' && existsSync(devVenvPython)) {
    return devVenvPython
  }
  return process.platform === 'win32' ? 'python.exe' : 'python3'
}

function getMainScript(): string {
  if (app.isPackaged) return ''
  // In development app.getAppPath() resolves to the compiled electron dir
  // (frontend/dist-electron), so main.py at the project ROOT is two levels up.
  return join(app.getAppPath(), '..', '..', 'main.py')
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

// UI-001 / ZERO OWNER MANUAL OPERATIONS (.claude/WORKING_MODEL.md, .claude/DECISIONS.md).
//
// Pipeline visual pixel-perfect contra o MASTER, sem NENHUM passo manual do
// Alex: a ZARA captura sua própria janela, registra o viewport, decide
// sozinha se a mudança é relevante, e sincroniza com o repo remoto (onde
// Opus/Sonnet rodam) só quando realmente há novidade — nunca a cada vez que
// o Alex simplesmente abre o app.
//
// findRepoRoot() sobe a árvore de diretórios a partir do executável/appPath
// procurando ".git" — funciona tanto em dev (app.getAppPath() ==
// frontend/dist-electron) quanto empacotado (o EXE roda de dentro de
// frontend/release*/win-unpacked/, vários níveis abaixo da raiz do repo; o
// truque fixo de "../.." usado antes só era correto em dev). Fora de um
// checkout do repo (instalação standalone) retorna null e tudo aqui vira
// no-op silencioso — nunca afeta o uso normal da ZARA.
function findRepoRoot(): string | null {
  let dir = app.isPackaged ? join(process.execPath, '..') : app.getAppPath()
  for (let i = 0; i < 8; i += 1) {
    if (existsSync(join(dir, '.git'))) return dir
    const parent = join(dir, '..')
    if (parent === dir) return null
    dir = parent
  }
  return null
}

function getUiTestDir(repoRoot: string): string {
  return join(repoRoot, '.zara-tests', 'ui')
}

function gitHead(repoRoot: string): string | null {
  try {
    return execFileSync('git', ['rev-parse', 'HEAD'], { cwd: repoRoot, encoding: 'utf-8' }).trim()
  } catch {
    return null
  }
}

function runGit(args: string[], cwd: string): Promise<void> {
  return new Promise((resolve, reject) => {
    execFile('git', args, { cwd, timeout: 20000 }, (error) => {
      if (error) reject(error)
      else resolve()
    })
  })
}

interface CaptureState {
  last_screenshot_sha256?: string
  last_synced_head?: string
}

function readCaptureState(uiDir: string): CaptureState {
  try {
    return JSON.parse(readFileSync(join(uiDir, '.capture-state.json'), 'utf-8'))
  } catch {
    return {}
  }
}

function writeCaptureState(uiDir: string, state: CaptureState): void {
  writeFileSync(join(uiDir, '.capture-state.json'), JSON.stringify(state, null, 2), 'utf-8')
}

// Só existe .zara-tests/ui/QA_REQUEST.flag quando o Chief of Staff (sessão
// remota) marcou que precisa de evidência nova pra uma task visual ativa —
// é o único canal pelo qual "existe task ativa" chega até a máquina do Alex,
// já que os dois lados só se falam via git. Consumido (apagado) assim que
// vira snapshot.
async function syncUiSnapshotIfNeeded(win: BrowserWindow, pngBuffer: Buffer): Promise<void> {
  const repoRoot = findRepoRoot()
  if (!repoRoot) return

  const uiDir = getUiTestDir(repoRoot)
  mkdirSync(join(uiDir, 'history'), { recursive: true })

  // Puxa o que a sessão remota já publicou (pedido de QA, master.png novo,
  // etc.) antes de decidir — best-effort, nunca bloqueia por estar offline.
  await runGit(['pull', '--ff-only'], repoRoot).catch(() => undefined)

  const newHash = createHash('sha256').update(pngBuffer).digest('hex')
  const state = readCaptureState(uiDir)
  const currentHead = gitHead(repoRoot)
  const markerPath = join(uiDir, 'QA_REQUEST.flag')
  const hasRequest = existsSync(markerPath)

  const needSnapshot =
    newHash !== state.last_screenshot_sha256 ||
    (currentHead !== null && currentHead !== state.last_synced_head) ||
    hasRequest

  // Viewport sempre fica atualizado no disco local — é diagnóstico barato —
  // mas só entra no commit quando o snapshot abaixo realmente acontece.
  writeViewportJson(win, uiDir, currentHead)

  if (!needSnapshot) return

  const targetPath = join(uiDir, 'electron-real.png')
  if (existsSync(targetPath)) {
    const stamp = new Date().toISOString().replace(/[:.]/g, '-')
    renameSync(targetPath, join(uiDir, 'history', `electron-real-${stamp}.png`))
  }
  writeFileSync(targetPath, pngBuffer)
  writeCaptureState(uiDir, { last_screenshot_sha256: newHash, last_synced_head: currentHead ?? state.last_synced_head })
  if (hasRequest) {
    try { unlinkSync(markerPath) } catch { /* já sumiu, tudo bem */ }
  }

  // Commit + push escopados SÓ em .zara-tests/ui — nunca junto de commit de
  // código do Alex, nunca --force. Se falhar (offline, sem git configurado),
  // o print continua salvo localmente; só a sincronização remota não rola.
  try {
    await runGit(['add', '--', '.zara-tests/ui'], repoRoot)
    await runGit(['diff', '--cached', '--quiet', '--', '.zara-tests/ui'], repoRoot)
    // sem erro acima == sem diferença staged == nada pra commitar de verdade
    return
  } catch {
    // diff --quiet saiu com erro == HA diferença staged == segue pro commit
  }
  try {
    await runGit(['commit', '-m', 'ui: snapshot automatico electron-real (zero-manual-ops)'], repoRoot)
    await runGit(['push'], repoRoot)
    console.log('[UI-001] snapshot sincronizado com o repo remoto.')
  } catch (error) {
    console.warn('[UI-001] snapshot salvo local, mas sync remoto falhou (best-effort):', error)
  }
}

// UI-001: captura o Electron real de verdade — nunca pede pro Alex tirar
// print. Roda sozinha quando a janela aparece em primeiro plano (nunca no
// boot silencioso pra bandeja) e de novo, com debounce, a cada resize.
async function captureElectronScreenshot(win: BrowserWindow): Promise<void> {
  try {
    if (win.isDestroyed() || !win.isVisible()) return
    const image = await win.webContents.capturePage()
    await syncUiSnapshotIfNeeded(win, image.toPNG())
  } catch (error) {
    // Best-effort: nunca deve afetar o uso normal da ZARA.
    console.warn('[UI-001] falha ao capturar electron-real.png:', error)
  }
}

function writeViewportJson(win: BrowserWindow, uiDir: string, sourceHead: string | null): void {
  const bounds = win.getBounds()
  const contentBounds = win.getContentBounds()
  const payload = {
    window_width: bounds.width,
    window_height: bounds.height,
    content_width: contentBounds.width,
    content_height: contentBounds.height,
    device_pixel_ratio: null as number | null,
    zoom: win.webContents.getZoomFactor(),
    timestamp: new Date().toISOString(),
    source_head: sourceHead,
  }
  win.webContents.executeJavaScript('window.devicePixelRatio').then((dpr) => {
    payload.device_pixel_ratio = dpr
    writeFileSync(join(uiDir, 'current_viewport.json'), JSON.stringify(payload, null, 2), 'utf-8')
  }).catch(() => {
    writeFileSync(join(uiDir, 'current_viewport.json'), JSON.stringify(payload, null, 2), 'utf-8')
  })
}

// UI-001: mesmo diagnóstico de viewport, mas chamado sozinho (fora do fluxo
// de captura de screenshot) nos resizes intermediários — nunca dispara git.
async function writeViewportDiagnostics(win: BrowserWindow): Promise<void> {
  try {
    if (win.isDestroyed()) return
    const repoRoot = findRepoRoot()
    if (!repoRoot) return
    const uiDir = getUiTestDir(repoRoot)
    mkdirSync(uiDir, { recursive: true })
    writeViewportJson(win, uiDir, gitHead(repoRoot))
  } catch (error) {
    console.warn('[UI-001] falha ao gravar current_viewport.json:', error)
  }
}

function rejectPendingRequests(reason: string): void {
  for (const [, pending] of pendingRequests) {
    pending.reject(new Error(reason))
  }
  pendingRequests.clear()
}

function startPythonSidecar(): Promise<void> {
  if (pythonProcess && isPythonReady) return Promise.resolve()
  if (pythonProcess && pythonReadinessPromise) return pythonReadinessPromise
  if (pythonProcess) return Promise.reject(new Error('Python sidecar já está iniciando'))
  if (isStoppingPython) return Promise.reject(new Error('Python sidecar está encerrando'))

  return new Promise((resolve, reject) => {
    let settled = false
    let startupTimer: ReturnType<typeof setTimeout> | null = null
    const settleResolve = () => {
      if (settled) return
      settled = true
      if (startupTimer) clearTimeout(startupTimer)
      resolve()
    }
    const settleReject = (error: Error) => {
      if (settled) return
      settled = true
      if (startupTimer) clearTimeout(startupTimer)
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
    env.ZARA_PARENT_PID = String(process.pid)

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
      if (pythonProcess !== child) return
      const wasReady = isPythonReady
      pythonProcess = null
      isPythonReady = false
      rejectPendingRequests('Python process exited')
      if (!wasReady) {
        settleReject(new Error(`Python sidecar exited before ready (code ${code})`))
      }
    })

    // ZARA-SIDECAR-TIMEOUT-MARGEM-001: boot a frio medido nesta madrugada
    // ficou em ~30-35s (varias repeticoes, IPC bruto contra o binario real).
    // 45s deixava so 10-15s de folga -- pouco, com o disco C perto do limite
    // (~9GB livres) deixando a extracao do PyInstaller onefile mais lenta em
    // dias ruins. 75s da margem real sem esconder uma falha de verdade por
    // muito tempo.
    startupTimer = setTimeout(() => {
      if (pythonProcess === child && !isPythonReady) {
        settleReject(new Error('Python sidecar startup timeout (75s)'))
        child.kill()
      }
    }, 75000)
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
    // ZARA-AEC-RENDERER-001: a voz da Kore vem em PCM para o renderer tocar.
    // É essa reprodução que dá ao AEC do Chromium o sinal de referência.
    case 'voice-output-audio':
      mainWindow?.webContents.send('voice-output-audio', msg.data)
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

// ZARA-BANDEJA-001 ---------------------------------------------------------

function mostrarAJanela(): void {
  if (!mainWindow || mainWindow.isDestroyed()) {
    createWindow()
    return
  }
  if (mainWindow.isMinimized()) mainWindow.restore()
  mainWindow.show()
  mainWindow.focus()
}

function sairDeVerdade(): void {
  saindoDeVerdade = true
  app.quit()
}

/** Está configurada para subir junto com o Windows? */
function sobeComOWindows(): boolean {
  try {
    return app.getLoginItemSettings({ args: ['--minimizada'] }).openAtLogin
  } catch {
    return false
  }
}

function definirInicioAutomatico(ligado: boolean): void {
  try {
    // `--minimizada` faz ela subir direto para a bandeja, sem abrir janela.
    app.setLoginItemSettings({
      openAtLogin: ligado,
      args: ligado ? ['--minimizada'] : [],
    })
  } catch (erro) {
    console.error('[Electron] nao consegui mudar o inicio automatico:', erro)
  }
}

/** Liga o início automático UMA vez, e nunca mais decide por ele.
 *
 * A ZARA precisa permanecer disponível em segundo plano, e isso exige ela
 * ligada. Mas se ele desligar essa opção no menu da bandeja, religar na próxima
 * abertura seria o app desfazendo a escolha dele — o mesmo defeito do botão de
 * mudo que ele já reclamou. O carimbo em disco existe para isso: marca que a
 * pergunta já foi respondida, e a resposta passa a ser dele.
 */
function ligarSozinhaNaPrimeiraVez(): void {
  try {
    const carimbo = join(app.getPath('userData'), 'inicio-automatico-decidido')
    if (existsSync(carimbo)) return
    definirInicioAutomatico(true)
    writeFileSync(carimbo, new Date().toISOString(), 'utf-8')
    atualizarMenuDaBandeja()
    console.log('[Electron] inicio automatico ligado (primeira vez)')
  } catch (erro) {
    console.error('[Electron] nao consegui decidir o inicio automatico:', erro)
  }
}

function montarBandeja(): void {
  if (tray) return
  const iconPath = getWindowIconPath()
  if (!existsSync(iconPath)) {
    // Sem ícone não há bandeja, e sem bandeja o X não pode esconder a janela —
    // ela ficaria inalcançável. Melhor voltar ao comportamento antigo.
    console.warn('[Electron] sem icone para a bandeja; a janela volta a fechar de verdade')
    saindoDeVerdade = true
    return
  }

  tray = new Tray(iconPath)
  tray.setToolTip('ZARA — clique para abrir')
  tray.on('click', mostrarAJanela)
  tray.on('double-click', mostrarAJanela)
  atualizarMenuDaBandeja()
}

function atualizarMenuDaBandeja(): void {
  if (!tray) return
  const ligado = sobeComOWindows()
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: 'Abrir a ZARA', click: mostrarAJanela },
    { type: 'separator' },
    {
      label: 'Ligar sozinha com o Windows',
      type: 'checkbox',
      checked: ligado,
      click: () => {
        definirInicioAutomatico(!ligado)
        atualizarMenuDaBandeja()
      },
    },
    { type: 'separator' },
    { label: 'Sair da ZARA', click: sairDeVerdade },
  ]))
}

function createWindow(): void {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.focus()
    return
  }

  const iconPath = getWindowIconPath()
  mainWindow = new BrowserWindow({
    // UI-001: a composição calibrada contra o MASTER (zara-home.css, blocos
    // "Calibração global"/"MASTER 1671×941") precisa de ~1377px de conteúdo
    // + até 222px de sidebar + padding — não cabe nos 1500px/1200px
    // anteriores. Nessa largura, `.zh-content` (overflow-y: auto, que pela
    // spec de CSS também vira overflow-x: auto) ficava rolável na horizontal
    // sem barra visível de aviso — a coluna direita (Ferramentas/Docker,
    // botão "Continuar") existe no código mas fica fora da área visível sem
    // rolar. Aumentando a janela padrão isso volta a aparecer sem rolagem.
    width: 1680,
    height: 980,
    minWidth: 1500,
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
    // ZARA-BANDEJA-001: quando o Windows a inicia sozinha, ela sobe calada,
    // direto para a bandeja. Uma janela pulando na frente do Alex toda vez que
    // ele liga o computador seria pior que não ter início automático.
    if (abriuMinimizada) return
    if (!windowRef.isDestroyed() && !windowRef.isVisible()) {
      windowRef.show()
      windowRef.focus()
    }
  }
  windowRef.once('ready-to-show', showWindow)
  windowRef.webContents.once('did-finish-load', showWindow)
  setTimeout(showWindow, 3000)

  // UI-001 / ZERO OWNER MANUAL OPERATIONS: mantém current_viewport.json E
  // electron-real.png alinhados com a janela real — sem flag, sem BAT, sem
  // gatilho manual. Só roda em primeiro plano (abriuMinimizada = boot
  // silencioso pra bandeja, nunca captura aí).
  let viewportDiagnosticsTimer: ReturnType<typeof setTimeout> | null = null
  const scheduleViewportDiagnostics = () => {
    if (abriuMinimizada) return
    if (viewportDiagnosticsTimer) clearTimeout(viewportDiagnosticsTimer)
    viewportDiagnosticsTimer = setTimeout(() => {
      void writeViewportDiagnostics(windowRef)
    }, 400)
  }
  let screenshotTimer: ReturnType<typeof setTimeout> | null = null
  const scheduleScreenshot = () => {
    if (abriuMinimizada) return
    if (screenshotTimer) clearTimeout(screenshotTimer)
    // Delay maior que o do viewport: dá tempo da UI assentar (fontes,
    // animação de entrada, dados carregados) antes de capturar o pixel.
    screenshotTimer = setTimeout(() => {
      void captureElectronScreenshot(windowRef)
    }, 2500)
  }
  windowRef.webContents.once('did-finish-load', scheduleViewportDiagnostics)
  windowRef.webContents.once('did-finish-load', scheduleScreenshot)
  windowRef.on('resize', scheduleViewportDiagnostics)
  windowRef.on('resize', scheduleScreenshot)
  windowRef.on('maximize', scheduleViewportDiagnostics)
  windowRef.on('maximize', scheduleScreenshot)
  windowRef.on('unmaximize', scheduleViewportDiagnostics)
  windowRef.on('unmaximize', scheduleScreenshot)

  // ZARA-BANDEJA-001: o X esconde; sair de verdade é pelo menu da bandeja.
  windowRef.on('close', (evento) => {
    if (saindoDeVerdade) return
    evento.preventDefault()
    windowRef.hide()
  })

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
  ipcMain.handle('send-message', (_event, payload) => sendToPython('send-message', payload))
  ipcMain.handle('interrupt', () => sendToPython('interrupt'))
  // ZARA-BOTAO-MUDO-001: calar a voz sem desligar o resto dela.
  ipcMain.handle('voice-mute', (_e, mudo?: boolean) => sendToPython('voice-mute', { mudo }))

  // ZARA-AEC-RENDERER-001. Microfone já limpo pelo AEC, ~23 blocos por segundo.
  // Vai sem request_id de propósito: usar sendToPython criaria uma promessa
  // pendente por bloco e o mapa de requisições cresceria sem parar, já que o
  // backend não responde a chunk de áudio.
  ipcMain.on('voice-mic-chunk', (_evento, pcm: string) => {
    if (!pythonProcess || !isPythonReady || !pcm) return
    try {
      pythonProcess.stdin?.write(
        JSON.stringify({ type: 'voice-mic-chunk', payload: { pcm } }) + '\n',
      )
    } catch {
      // Backend caindo: o próximo bloco tenta de novo. Não vale derrubar a
      // captura de áudio por causa de um bloco perdido.
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
  ipcMain.handle('action-execute', executeActionWithConfirmation)
  ipcMain.handle('action-list', () => sendToPython('action-list'))
  ipcMain.handle('system-metrics', () => sendToPython('system-metrics'))
  ipcMain.handle('self-status', () => sendToPython('self-status'))
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

// Se quem lia a saida deste processo sumir (um terminal fechado, um pipe
// cortado), qualquer console.log vira EPIPE e derruba o app inteiro com um
// dialogo de erro. Log nao pode matar a ZARA.
for (const canal of [process.stdout, process.stderr]) {
  canal.on('error', (erro: NodeJS.ErrnoException) => {
    if (erro?.code === 'EPIPE') return
  })
}
process.on('uncaughtException', (erro: NodeJS.ErrnoException) => {
  if (erro?.code === 'EPIPE') return
  throw erro
})

const gotSingleInstanceLock = app.requestSingleInstanceLock()
if (!gotSingleInstanceLock) {
  // Another ZARA instance is already running: do not start a second sidecar
  // (which would open the same SQLite/WAL data dir). Quit immediately.
  console.warn('[Electron] Outra instancia da ZARA ja esta em execucao. Encerrando esta.')
  app.quit()
} else {
  // Ensure lock is released on exit to prevent stale mutex on crash/kill
  app.on('will-quit', () => {
    if (gotSingleInstanceLock) {
      app.releaseSingleInstanceLock()
    }
  })
  app.on('second-instance', () => {
    // ZARA-BANDEJA-001: agora a janela pode estar escondida, não só minimizada.
    // `focus()` numa janela escondida não mostra nada, e clicar no atalho
    // pareceria não fazer efeito.
    mostrarAJanela()
  })

  app.whenReady().then(() => {
    // The interface is independent from backend startup. This guarantees that a
    // sidecar failure is visible to the user instead of producing a black window.
    setupIPC()

    // ZARA-AEC-RENDERER-001. Sem isto o getUserMedia do renderer é negado no
    // app empacotado e a ZARA fica surda em silêncio — sem erro visível.
    // Autoriza só microfone; qualquer outra permissão continua negada.
    session.defaultSession.setPermissionRequestHandler((_wc, permissao, responder) => {
      responder(permissao === 'media')
    })
    session.defaultSession.setPermissionCheckHandler(
      (_wc, permissao) => permissao === 'media',
    )

    pythonReadinessPromise = startPythonSidecar()
    void pythonReadinessPromise.catch((error) => {
      console.error('[Electron] Python backend unavailable:', error)
    })
    createWindow()
    montarBandeja()
    ligarSozinhaNaPrimeiraVez()

    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow()
    })
  })
}

// ZARA-SIDECAR-ORFAO-001
// Observado duas vezes em 2026-08-13: fechar a janela deixava um
// zara-backend.exe vivo, segurando o microfone e o banco. Duas causas, e as
// duas precisavam de conserta:
//
//  1. `child.kill()` matava só o BOOTLOADER. O sidecar é PyInstaller onefile:
//     o processo que criamos extrai o app e roda o programa de verdade num
//     processo FILHO. Matar o pai deixa o filho vivo — foi exatamente o que
//     apareceu na lista (pai de 7 MB morto, filho de 282 MB vivo).
//  2. O timer levava `.unref()`, então o Node não segurava o processo por ele.
//     Durante o encerramento o Electron morria antes dos 1,5 s e o kill nunca
//     chegava a rodar.
function killPythonTree(pid: number | undefined): void {
  if (!pid) return
  if (process.platform === 'win32') {
    try {
      // /T = árvore inteira, /F = à força. É o que alcança o filho do onefile.
      execFileSync('taskkill', ['/PID', String(pid), '/T', '/F'], {
        stdio: 'ignore',
        timeout: 4000,
      })
    } catch {
      // Já morreu, ou o pid sumiu. Os dois casos são o resultado desejado.
    }
    return
  }
  try {
    process.kill(pid, 'SIGKILL')
  } catch {
    /* já morreu */
  }
}

function stopPython(): void {
  const child = pythonProcess
  pythonProcess = null
  isPythonReady = false
  pythonReadinessPromise = null
  if (!child) return
  isStoppingPython = true
  lastPythonPid = child.pid
  rejectPendingRequests('Application shutting down')
  // Closing stdin gives the owned Python sidecar a clean EOF. Force-stop only
  // this exact child if it does not exit within the short grace period.
  child.stdin?.end()
  // Sem unref: durante o encerramento este timer PRECISA rodar, senão o
  // sidecar sobrevive ao app.
  const forceTimer = setTimeout(() => {
    if (child.exitCode === null) killPythonTree(child.pid)
    isStoppingPython = false
  }, 1500)
  child.once('exit', () => {
    clearTimeout(forceTimer)
    lastPythonPid = undefined
    isStoppingPython = false
  })
}

app.on('before-quit', () => {
  // ZARA-BANDEJA-001: `before-quit` também dispara em logoff/desligamento do
  // Windows, quando ninguém clicou em "Sair". Marcar aqui garante que o
  // `close` da janela não cancele o encerramento e deixe o processo pendurado.
  saindoDeVerdade = true
  stopPython()
})
app.on('window-all-closed', () => {
  // ZARA-BANDEJA-001: com a bandeja no ar, ficar sem janela é estado normal —
  // é assim que ela continua disponível em segundo plano. Encerrar aqui mataria o
  // sidecar e o Alex voltaria a ficar sem resposta no celular.
  if (tray && !saindoDeVerdade) return
  stopPython()
  if (process.platform !== 'darwin') app.quit()
})

// Última rede: `will-quit` é síncrono e roda depois de `before-quit`. Se o
// sidecar ainda não saiu pelo EOF, ele morre aqui — antes de o Electron
// desaparecer e transformá-lo em órfão.
app.on('will-quit', () => {
  if (lastPythonPid !== undefined) {
    killPythonTree(lastPythonPid)
    lastPythonPid = undefined
  }
})

app.on('web-contents-created', (_event, contents) => {
  contents.setWindowOpenHandler(({ url }) => {
    void shell.openExternal(url)
    return { action: 'deny' }
  })
})
