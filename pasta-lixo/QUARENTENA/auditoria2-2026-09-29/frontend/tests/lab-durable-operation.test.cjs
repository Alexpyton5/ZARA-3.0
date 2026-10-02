const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')

function load(storage, storageOverrides = {}) {
  const source = fs.readFileSync(
    path.join(__dirname, '../src/renderer/lib/labDurableOperation.ts'),
    'utf8',
  )
  const code = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText
  const exports = {}
  const localStorage = {
    getItem: key => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
    ...storageOverrides,
  }
  vm.runInNewContext(code, {
    exports,
    localStorage,
    globalThis: { crypto: { randomUUID: () => 'stable-id' } },
    Date,
    Math,
    JSON,
  })
  return exports
}

test('renderer crash keeps the request and restart confirms the same id once', async () => {
  const storage = new Map()
  const first = load(storage)
  await assert.rejects(
    first.runDurableLabMutation(
      { autopilot: async () => { throw new Error('renderer lost confirmation') } },
      'autopilot',
      { intent: 'Improve ZARA' },
    ),
    /renderer lost confirmation/,
  )

  const pending = JSON.parse(storage.get('zara.lab.pending-mutations.v1'))
  assert.equal(pending.length, 1)
  assert.equal(pending[0].requestId, 'lab-renderer-stable-id')

  const replayed = []
  const restarted = load(storage)
  const recovered = await restarted.recoverDurableLabMutations({
    autopilot: async (intent, requestId) => {
      replayed.push({ intent, requestId })
      return {
        success: true,
        accepted: true,
        operation_id: 'operation:1',
        state: 'QUEUED',
      }
    },
  })

  assert.equal(recovered, 1)
  assert.deepEqual(replayed, [{ intent: 'Improve ZARA', requestId: 'lab-renderer-stable-id' }])
  assert.deepEqual(JSON.parse(storage.get('zara.lab.pending-mutations.v1')), [])
})

test('confirmed mutation is removed and cannot be replayed', async () => {
  const storage = new Map()
  const client = load(storage)
  await client.runDurableLabMutation(
    { cancelMission: async () => ({
      success: true,
      accepted: true,
      operation_id: 'operation:cancel-1',
      state: 'QUEUED',
    }) },
    'cancel',
    { sessionId: 'session-1' },
  )
  assert.equal(await client.recoverDurableLabMutations({
    cancelMission: async () => assert.fail('confirmed operation must not replay'),
  }), 0)
})

test('storage failure is visible and prevents transport', async () => {
  const storage = new Map()
  let dispatches = 0
  const client = load(storage, {
    setItem: () => { throw new Error('quota exceeded') },
  })

  await assert.rejects(
    client.runDurableLabMutation(
      { autopilot: async () => { dispatches += 1 } },
      'autopilot',
      { intent: 'Improve ZARA' },
    ),
    /persist/i,
  )
  assert.equal(dispatches, 0)
})

test('unverified storage write prevents transport', async () => {
  const storage = new Map()
  let dispatches = 0
  const client = load(storage, { setItem: () => undefined })

  await assert.rejects(
    client.runDurableLabMutation(
      { autopilot: async () => { dispatches += 1 } },
      'autopilot',
      { intent: 'Improve ZARA' },
    ),
    /persist/i,
  )
  assert.equal(dispatches, 0)
})

test('transient admission failure stays pending and recovery reuses the same request id', async () => {
  const storage = new Map()
  const first = load(storage)
  const transient = await first.runDurableLabMutation(
    { autopilot: async () => ({
      success: false,
      accepted: false,
      state: 'REJECTED',
      code: 'OPERATION_ADMISSION_FAILED',
    }) },
    'autopilot',
    { intent: 'Improve ZARA' },
  )
  assert.equal(transient.code, 'OPERATION_ADMISSION_FAILED')
  assert.equal(JSON.parse(storage.get('zara.lab.pending-mutations.v1')).length, 1)

  const replayedIds = []
  const recovered = await load(storage).recoverDurableLabMutations({
    autopilot: async (_intent, requestId) => {
      replayedIds.push(requestId)
      return { success: false, accepted: false, state: 'REJECTED', code: 'OPERATION_ADMISSION_FAILED' }
    },
  })
  assert.equal(recovered, 0)
  assert.deepEqual(replayedIds, ['lab-renderer-stable-id'])
  assert.equal(JSON.parse(storage.get('zara.lab.pending-mutations.v1')).length, 1)
})

test('unknown confirmation stays visible in the journal and recovery never creates a duplicate operation', async () => {
  const storage = new Map()
  const first = load(storage)
  const firstRequestIds = []
  await assert.rejects(first.runDurableLabMutation({
    roomMessage: async (_sessionId, _content, requestId) => {
      firstRequestIds.push(requestId)
      throw new Error('A confirmação do Lab ainda não chegou. A operação op-7 foi preservada para retomada.')
    },
  }, 'roomMessage', { sessionId: 'session-1', text: 'Improve ZARA' }))

  assert.equal(JSON.parse(storage.get('zara.lab.pending-mutations.v1')).length, 1)
  const replayedRequestIds = []
  const recovered = await load(storage).recoverDurableLabMutations({
    roomMessage: async (_sessionId, _content, requestId) => {
      replayedRequestIds.push(requestId)
      return {
        success: true,
        accepted: true,
        operation_id: 'op-7',
        state: 'QUEUED',
      }
    },
  })
  assert.equal(recovered, 1)
  assert.deepEqual(replayedRequestIds, firstRequestIds)
  assert.deepEqual(JSON.parse(storage.get('zara.lab.pending-mutations.v1')), [])
})

test('missing optional API stays pending and is visible to the caller', async () => {
  const storage = new Map()
  const client = load(storage)

  await assert.rejects(
    client.runDurableLabMutation({}, 'submit', { sessionId: 's1', text: 'continue' }),
    /unavailable/i,
  )
  assert.equal(JSON.parse(storage.get('zara.lab.pending-mutations.v1')).length, 1)
  assert.equal(await client.recoverDurableLabMutations({}), 0)
  assert.equal(JSON.parse(storage.get('zara.lab.pending-mutations.v1')).length, 1)
})

test('success label without confirmed admission does not conclude the journal', async () => {
  const storage = new Map()
  const client = load(storage)
  await client.runDurableLabMutation(
    { cancelMission: async () => ({ success: true }) },
    'cancel',
    { sessionId: 'session-1' },
  )

  assert.equal(JSON.parse(storage.get('zara.lab.pending-mutations.v1')).length, 1)
})

test('factual terminal rejection concludes the journal', async () => {
  const storage = new Map()
  const client = load(storage)
  const result = await client.runDurableLabMutation(
    { autopilot: async () => ({
      success: false,
      accepted: false,
      state: 'REJECTED',
      code: 'INVALID_OPERATION',
    }) },
    'autopilot',
    { intent: '' },
  )

  assert.equal(result.code, 'INVALID_OPERATION')
  assert.deepEqual(JSON.parse(storage.get('zara.lab.pending-mutations.v1')), [])
})
