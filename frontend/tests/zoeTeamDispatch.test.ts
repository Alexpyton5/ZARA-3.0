import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { startZoeBridge } from '../src/zoeBridge'
import { createZoeTeamDispatch, remoteTeamRequestId } from '../src/zoeTeamDispatch'

const valid = { kind: 'team-mission', channel: 'whatsapp', message_id: 'wamid.owner-1', objective: 'Organize a equipe para revisar o projeto' }

test('ordinary PC commands retain the existing receiver', async () => {
  const calls: unknown[] = []
  const route = createZoeTeamDispatch(async (type, payload) => { calls.push([type, payload]); return { old: true } }, async () => { throw Error('unexpected') })
  assert.deepEqual(await route('zoe-remote-command', { message_id: '1', text: 'abra o bloco de notas' }), { old: true })
  assert.equal(calls.length, 1)
})

test('remote work uses durable submit with original stable message ID and never claims completion', async () => {
  const calls: unknown[] = []
  const route = createZoeTeamDispatch(async () => { throw Error('unexpected') }, async (...args) => {
    calls.push(args); return { success: true, accepted: true, confirmed: true, operation_id: 'op-1', state: 'ADMITTED' }
  })
  const result = await route('zoe-remote-command', valid) as Record<string, unknown>
  assert.deepEqual(calls[0], ['lab.v1.submit', { objective: valid.objective }, remoteTeamRequestId('whatsapp', valid.message_id)])
  assert.equal(result.mission_complete, false)
  assert.equal(result.delivery, 'DISPATCH_AUTHORIZED')
  assert.equal(result.operation_id, 'op-1')
  assert.equal(result.reply_to_message_id, valid.message_id)
})

test('reject invalid remote envelopes before any backend side effect', async () => {
  let calls = 0
  const route = createZoeTeamDispatch(async () => { calls++; return {} }, async () => { calls++; return {} })
  for (const envelope of [
    { ...valid, message_id: '' }, { ...valid, message_id: 'a'.repeat(161) },
    { ...valid, channel: 'assistant' }, { ...valid, channel: ['whatsapp'] }, { ...valid, objective: '' }, { ...valid, objective: 'a'.repeat(4001) },
    { ...valid, objective: 12 }, { ...valid, text: 'conflicting source' },
    { ...valid, audio_path: '../secret' }, { ...valid, paid_allowed: true }, { ...valid, kind: 'arbitrary-shell' },
  ]) {
    const result = await route('zoe-remote-command', envelope) as Record<string, unknown>
    assert.equal(result.success, false)
  }
  assert.equal(calls, 0)
})

test('failed admission or mismatched confirmation cannot become acknowledged work', async () => {
  for (const receipt of [
    { success: false, accepted: false, code: 'IDEMPOTENCY_CONFLICT' },
    { success: true, accepted: true, confirmed: false, operation_id: '1' },
    { success: true, accepted: true, confirmed: true },
  ]) {
    const route = createZoeTeamDispatch(async () => ({}), async () => receipt)
    const result = await route('zoe-remote-command', valid) as Record<string, unknown>
    assert.equal(result.success, false)
    assert.equal(result.mission_complete, false)
    assert.notEqual(result.delivery, 'DISPATCH_AUTHORIZED')
  }
})

test('request identity survives retries and distinguishes sources; content conflicts remain ledger responsibility', () => {
  assert.equal(remoteTeamRequestId('whatsapp', valid.message_id), 'zoe-team:3b048a0c79be254ba19ca988a87a793d9ba0f04ff2003df3cd7c0b4236887bf9')
  assert.equal(remoteTeamRequestId('whatsapp', '1'), remoteTeamRequestId('whatsapp', '1'))
  assert.notEqual(remoteTeamRequestId('whatsapp', '1'), remoteTeamRequestId('muse', '1'))
  assert.match(remoteTeamRequestId('whatsapp', 'ID com / caracteres'), /^[A-Za-z0-9_.:-]{1,120}$/)
})

test('real HTTP bridge authenticates a team request before durable admission', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'zoe-team-'))
  let calls = 0
  const route = createZoeTeamDispatch(async () => { throw Error('unexpected') }, async () => {
    calls++; return { success: true, accepted: true, confirmed: true, operation_id: 'op-http' }
  })
  const bridge = await startZoeBridge(directory, route)
  try {
    const connection = JSON.parse(readFileSync(join(directory, 'connection.json'), 'utf8'))
    const send = (token: string) => fetch(`http://127.0.0.1:${bridge.port}/v1/command`, {
      method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: 'zoe-remote-command', payload: valid }),
    })
    assert.equal((await send('invalid')).status, 401)
    assert.equal(calls, 0)
    const response = await send(connection.token)
    assert.equal(response.status, 200)
    const receipt = await response.json() as Record<string, unknown>
    assert.equal(receipt.delivery, 'DISPATCH_AUTHORIZED')
    assert.equal(receipt.mission_complete, false)
    assert.equal(calls, 1)
  } finally { await bridge.close(); rmSync(directory, { recursive: true, force: true }) }
})

test('backend exception returns unknown outcome without immediate duplicate dispatch', async () => {
  let calls = 0
  const route = createZoeTeamDispatch(async () => ({}), async () => { calls++; throw Error('secret backend detail') })
  const result = await route('zoe-remote-command', valid) as Record<string, unknown>
  assert.equal(result.success, false)
  assert.equal(result.delivery, 'UNCONFIRMED')
  assert.equal(calls, 1)
  assert.equal(JSON.stringify(result).includes('secret backend detail'), false)
})
