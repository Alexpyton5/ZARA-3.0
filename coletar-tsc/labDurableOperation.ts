type PendingLabMutation = {
  requestId: string
  kind: 'autopilot' | 'submit' | 'cancel' | 'roomMessage'
  payload: Record<string, string>
}

type LabMutationApi = {
  roomMessage?: (sessionId: string | undefined, content: string, requestId?: string) => Promise<any>
  autopilot?: (intent: string, requestId?: string) => Promise<any>
  submit?: (sessionId: string, text: string, requestId?: string) => Promise<any>
  cancelMission?: (sessionId: string, requestId?: string) => Promise<any>
}

const STORAGE_KEY = 'zara.lab.pending-mutations.v1'

const TERMINAL_REJECTION_CODES = new Set([
  'IDEMPOTENCY_CONFLICT',
  'INVALID_OPERATION',
])

function storageError(action: string, cause?: unknown): Error {
  const detail = cause instanceof Error && cause.message ? `: ${cause.message}` : ''
  return new Error(`Failed to ${action} durable Lab mutation journal${detail}`)
}

function readPending(): PendingLabMutation[] {
  try {
    const value = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
    return Array.isArray(value) ? value.filter(item =>
      item && typeof item.requestId === 'string'
      && ['autopilot', 'submit', 'cancel', 'roomMessage'].includes(item.kind)
      && item.payload && typeof item.payload === 'object',
    ) : []
  } catch (error) {
    throw storageError('read', error)
  }
}

function writePending(items: PendingLabMutation[]): void {
  const serialized = JSON.stringify(items)
  try {
    localStorage.setItem(STORAGE_KEY, serialized)
    if (localStorage.getItem(STORAGE_KEY) !== serialized) {
      throw storageError('verify persisted')
    }
  } catch (error) {
    if (error instanceof Error && error.message.startsWith('Failed to ')) throw error
    throw storageError('persist', error)
  }
}

function removePending(requestId: string): void {
  writePending(readPending().filter(item => item.requestId !== requestId))
}

function nextRequestId(): string {
  const random = globalThis.crypto?.randomUUID?.() || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
  return `lab-renderer-${random}`
}

async function invoke(api: LabMutationApi, item: PendingLabMutation): Promise<any> {
  if (item.kind === 'roomMessage') {
    if (typeof api.roomMessage !== 'function') throw new Error('Lab mutation API unavailable: roomMessage')
    return api.roomMessage(item.payload.sessionId || undefined, item.payload.text, item.requestId)
  }
  if (item.kind === 'autopilot') {
    if (typeof api.autopilot !== 'function') throw new Error('Lab mutation API unavailable: autopilot')
    return api.autopilot(item.payload.intent, item.requestId)
  }
  if (item.kind === 'submit') {
    if (typeof api.submit !== 'function') throw new Error('Lab mutation API unavailable: submit')
    return api.submit(item.payload.sessionId, item.payload.text, item.requestId)
  }
  if (typeof api.cancelMission !== 'function') throw new Error('Lab mutation API unavailable: cancel')
  return api.cancelMission(item.payload.sessionId, item.requestId)
}

function concludesJournal(result: any): boolean {
  if (!result || typeof result !== 'object') return false
  if (
    result.success === true
    && result.accepted === true
    && typeof result.operation_id === 'string'
    && result.operation_id.length > 0
    && result.state === 'QUEUED'
  ) return true
  return result.success === false
    && result.accepted === false
    && result.state === 'REJECTED'
    && TERMINAL_REJECTION_CODES.has(result.code)
}

/** Persist before transport; delete only after server confirmation reaches this renderer. */
export async function runDurableLabMutation(
  api: LabMutationApi,
  kind: PendingLabMutation['kind'],
  payload: Record<string, string>,
): Promise<any> {
  const item: PendingLabMutation = { requestId: nextRequestId(), kind, payload }
  writePending([...readPending(), item])
  const result = await invoke(api, item)
  if (concludesJournal(result)) removePending(item.requestId)
  return result
}

/** Replay only the exact persisted request id after a renderer/app restart. */
export async function recoverDurableLabMutations(api: LabMutationApi): Promise<number> {
  let recovered = 0
  for (const item of readPending()) {
    try {
      const result = await invoke(api, item)
      if (concludesJournal(result)) {
        removePending(item.requestId)
        recovered += 1
      }
    } catch {
      // Keep it durable. A later visible/mounted cycle can retry the same id.
    }
  }
  return recovered
}
