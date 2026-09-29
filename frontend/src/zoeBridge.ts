import { createServer, type Server } from 'node:http'
import { randomBytes, timingSafeEqual } from 'node:crypto'
import { appendFileSync, mkdirSync, readFileSync, renameSync, unlinkSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

type Dispatch = (type: string, payload?: Record<string, unknown>) => Promise<unknown>
type ActionSpec = { name?: string; risk?: string; capability?: string; requires_confirmation?: boolean }

export type ZoeBridge = {
  port: number
  close: () => Promise<void>
}

const MAX_BODY_BYTES = 32 * 1024
const ALLOWED_CAPABILITIES = new Set(['READ_ONLY', 'PC_CONTROL'])
// Registry metadata alone is not enough: some old actions labelled READ_ONLY
// can run macros or navigate a browser. Keep a reviewed, small first slice.
const ALLOWED_ACTIONS = new Set([
  'system_time', 'system_metrics', 'system_info', 'audio_status',
  'os_wifi_status', 'os_bluetooth_status', 'os_power_plan_list',
  'vision_screenshot', 'vision_ocr', 'vision_read_screen', 'vision_find_text',
  'os_notify', 'window_focus_named', 'window_minimize', 'window_maximize',
  'window_restore', 'os_volume', 'audio_mute', 'audio_unmute',
  'computer_foreground', 'computer_list_windows', 'computer_focus_window',
  'computer_click', 'computer_scroll', 'computer_press_key', 'computer_type_text',
  'computer_command',
  'input_type_text', 'input_hotkey',
])
const AUDITED_INPUT_ACTIONS = new Set([
  'computer_focus_window', 'computer_click', 'computer_scroll', 'computer_press_key', 'computer_type_text',
  'computer_command', 'input_type_text', 'input_hotkey',
])

function bridgeAllows(name: string, spec: ActionSpec | undefined): boolean {
  return ALLOWED_ACTIONS.has(name) && spec?.risk === 'LOW' && !spec.requires_confirmation
    && ALLOWED_CAPABILITIES.has(spec.capability ?? '')
}

export async function startZoeBridge(directory: string, dispatch: Dispatch): Promise<ZoeBridge> {
  mkdirSync(directory, { recursive: true, mode: 0o700 })
  const audit = (action: string, outcome: 'requested' | 'success' | 'failed'): boolean => {
    if (!AUDITED_INPUT_ACTIONS.has(action)) return true
    try {
      appendFileSync(join(directory, 'audit.jsonl'), JSON.stringify({ at: new Date().toISOString(), action, outcome }) + '\n', { encoding: 'utf8', mode: 0o600 })
      return true
    } catch { return false }
  }
  const token = randomBytes(32).toString('hex')
  const tokenBuffer = Buffer.from(token, 'utf8')
  const connectionPath = join(directory, 'connection.json')

  const server: Server = createServer(async (request, response) => {
    response.setHeader('Cache-Control', 'no-store')
    response.setHeader('Content-Type', 'application/json; charset=utf-8')
    const reply = (status: number, body: unknown) => {
      response.writeHead(status)
      response.end(JSON.stringify(body))
    }

    if (request.method !== 'POST' || request.url !== '/v1/command') {
      reply(404, { success: false, error: 'Rota não encontrada' })
      return
    }
    const supplied = request.headers.authorization?.replace(/^Bearer /, '') ?? ''
    const suppliedBuffer = Buffer.from(supplied, 'utf8')
    if (suppliedBuffer.length !== tokenBuffer.length || !timingSafeEqual(suppliedBuffer, tokenBuffer)) {
      reply(401, { success: false, error: 'Não autorizado' })
      return
    }
    if (request.headers['content-type']?.split(';')[0]?.trim() !== 'application/json') {
      reply(415, { success: false, error: 'Envie JSON' })
      return
    }

    const chunks: Buffer[] = []
    let bytes = 0
    try {
      for await (const chunk of request) {
        const part = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)
        bytes += part.length
        if (bytes > MAX_BODY_BYTES) {
          reply(413, { success: false, error: 'Pedido grande demais' })
          return
        }
        chunks.push(part)
      }
      const command: unknown = JSON.parse(Buffer.concat(chunks).toString('utf8'))
      if (!command || typeof command !== 'object' || Array.isArray(command)) {
        reply(400, { success: false, error: 'Pedido inválido' })
        return
      }
      const { type, payload } = command as { type?: unknown; payload?: unknown }
      if (typeof type !== 'string' || (payload !== undefined && (!payload || typeof payload !== 'object' || Array.isArray(payload)))) {
        reply(400, { success: false, error: 'Pedido inválido' })
        return
      }
      const params = (payload ?? {}) as Record<string, unknown>
      if (type === 'status') {
        reply(200, { success: true, bridge: 'ready', zoe_account: 'not_verified' })
        return
      }
      if (type === 'action-list') {
        const actions = await dispatch('action-list') as Record<string, ActionSpec>
        const allowed = Object.fromEntries(Object.entries(actions).filter(([name, spec]) => bridgeAllows(name, spec)))
        reply(200, { success: true, actions: allowed })
        return
      }
      if (type === 'action-execute') {
        const action = params.action
        const actionParams = params.params ?? {}
        if (typeof action !== 'string' || !action || !actionParams || typeof actionParams !== 'object' || Array.isArray(actionParams)) {
          reply(400, { success: false, error: 'Ação inválida' })
          return
        }
        const cleanParams = actionParams as Record<string, unknown>
        if ('confirm' in cleanParams || 'confirmation_id' in cleanParams || 'action_fingerprint' in cleanParams || '_zara_confirmation_proof' in cleanParams) {
          reply(403, { success: false, error: 'Confirmação exige a interface da ZARA' })
          return
        }
        const actions = await dispatch('action-list') as Record<string, ActionSpec>
        const spec = actions?.[action]
        if (!bridgeAllows(action, spec)) {
          reply(403, { success: false, error: 'Ação indisponível nesta ponte' })
          return
        }
        if (action === 'vision_screenshot' && 'path' in cleanParams) {
          reply(403, { success: false, error: 'A captura usa apenas a pasta temporária da ZARA' })
          return
        }
        if (action === 'vision_read_screen' && cleanParams.question) {
          reply(403, { success: false, error: 'Descrição por API externa indisponível nesta ponte' })
          return
        }
        if (!audit(action, 'requested')) {
          reply(503, { success: false, error: 'Registro de ações indisponível' })
          return
        }
        let result: unknown
        try {
          result = await dispatch('action-execute', { action, params: cleanParams })
        } catch (error) {
          audit(action, 'failed')
          throw error
        }
        const body = result as { success?: boolean; result?: { success?: boolean } } | null
        audit(action, body?.success !== false && body?.result?.success !== false ? 'success' : 'failed')
        reply(200, result)
        return
      }
      if (type === 'lab-v1-snapshot') {
        const sessionId = params.session_id
        if (sessionId !== undefined && (typeof sessionId !== 'string' || sessionId.length > 128)) {
          reply(400, { success: false, error: 'Sessão inválida' })
          return
        }
        reply(200, await dispatch('lab-v1-snapshot', sessionId ? { session_id: sessionId } : {}))
        return
      }
      if (type === 'memory-user-search') {
        const query = params.query
        if (typeof query !== 'string' || !query.trim() || query.length > 300) {
          reply(400, { success: false, error: 'Busca de memória inválida' })
          return
        }
        reply(200, await dispatch('memory-user-search', { query: query.trim(), limit: 5 }))
        return
      }
      if (type === 'project-memory-context') {
        reply(200, await dispatch('project-memory-context'))
        return
      }
      reply(403, { success: false, error: 'Comando indisponível nesta ponte' })
    } catch (error) {
      const isSyntax = error instanceof SyntaxError
      reply(isSyntax ? 400 : 503, { success: false, error: isSyntax ? 'JSON inválido' : 'ZARA indisponível' })
    }
  })

  server.requestTimeout = 70_000
  server.headersTimeout = 10_000
  try {
    await new Promise<void>((resolve, reject) => {
      server.once('error', reject)
      server.listen(0, '127.0.0.1', resolve)
    })
    const address = server.address()
    if (!address || typeof address === 'string') throw new Error('Porta local indisponível')
    const tempPath = join(directory, `connection-${process.pid}.tmp`)
    writeFileSync(tempPath, JSON.stringify({ host: '127.0.0.1', port: address.port, token, version: 1 }), { encoding: 'utf8', mode: 0o600 })
    renameSync(tempPath, connectionPath)
    return {
      port: address.port,
      close: async () => {
        try {
          const current = JSON.parse(readFileSync(connectionPath, 'utf8')) as { token?: string }
          if (current.token === token) unlinkSync(connectionPath)
        } catch { /* Already removed or replaced by a newer instance. */ }
        await new Promise<void>((resolve) => server.close(() => resolve()))
      },
    }
  } catch (error) {
    try { server.close() } catch { /* Never started listening. */ }
    throw error
  }
}
