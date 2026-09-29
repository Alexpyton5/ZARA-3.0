import assert from 'node:assert/strict'
import test from 'node:test'

import { runDurableLabMutation } from '../src/renderer/lib/labDurableOperation'

class MemoryStorage {
  private values = new Map<string, string>()
  getItem(key: string) { return this.values.get(key) ?? null }
  setItem(key: string, value: string) { this.values.set(key, value) }
  removeItem(key: string) { this.values.delete(key) }
}

const storageKey = 'zara.lab.pending-mutations.v1'

test('durable Lab journal clears only after dispatch authorization is confirmed', async () => {
  const storage = new MemoryStorage()
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: storage })
  let observedRequestId = ''

  const result = await runDurableLabMutation({
    submit: async (_sessionId, _text, requestId) => {
      observedRequestId = requestId || ''
      return {
        success: true,
        accepted: true,
        confirmed: true,
        state: 'DISPATCH_AUTHORIZED',
        operation_id: 'operation:confirmed',
      }
    },
  }, 'submit', { sessionId: 'session-1', text: 'Continue' })

  assert.equal(result.confirmed, true)
  assert.match(observedRequestId, /^lab-renderer-/)
  assert.deepEqual(JSON.parse(storage.getItem(storageKey) || '[]'), [])
})

test('durable Lab journal stays recoverable when confirmation is uncertain', async () => {
  const storage = new MemoryStorage()
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: storage })

  await runDurableLabMutation({
    cancelMission: async () => ({
      success: false,
      accepted: true,
      confirmed: false,
      state: 'ADMITTED',
      operation_id: 'operation:uncertain',
      code: 'CONFIRMATION_OUTCOME_UNKNOWN',
    }),
  }, 'cancel', { sessionId: 'session-1' })

  const pending = JSON.parse(storage.getItem(storageKey) || '[]')
  assert.equal(pending.length, 1)
  assert.equal(pending[0].payload.sessionId, 'session-1')
})
