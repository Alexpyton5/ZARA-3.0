const test = require('node:test')
const assert = require('node:assert/strict')
const { mkdtempSync, readFileSync, rmSync } = require('node:fs')
const { tmpdir } = require('node:os')
const { join, resolve, sep } = require('node:path')
const { startZoeBridge } = require('../dist-electron/zoeBridge.js')

test('Zoe bridge requires its token and limits the commands and actions', async () => {
  const root = mkdtempSync(join(tmpdir(), 'zara-zoe-bridge-'))
  const calls = []
  const actions = {
    os_wifi_status: { risk: 'LOW', capability: 'READ_ONLY' },
    vision_screenshot: { risk: 'LOW', capability: 'READ_ONLY' },
    os_notify: { risk: 'LOW', capability: 'PC_CONTROL' },
    computer_foreground: { risk: 'LOW', capability: 'READ_ONLY' },
    computer_click: { risk: 'LOW', capability: 'PC_CONTROL' },
    input_type_text: { risk: 'LOW', capability: 'PC_CONTROL' },
    macro_run: { risk: 'LOW', capability: 'READ_ONLY' },
    os_delete: { risk: 'HIGH', capability: 'FILES_MUTATE' },
  }
  const bridge = await startZoeBridge(root, async (type, payload) => {
    calls.push({ type, payload })
    if (type === 'action-list') return actions
    if (type === 'action-execute') return { success: true, result: { output: 'Wi-Fi ligado', verificado: true } }
    if (type === 'lab-v1-snapshot') return { success: true, sessions: [] }
    if (type === 'memory-user-search') return { success: true, hits: [] }
    if (type === 'project-memory-context') return { success: true, projects: [] }
    throw new Error('unexpected dispatch')
  })
  const connection = JSON.parse(readFileSync(join(root, 'connection.json'), 'utf8'))
  const command = async (type, payload, token = connection.token) => {
    const response = await fetch(`http://127.0.0.1:${bridge.port}/v1/command`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ type, payload }),
    })
    return { code: response.status, body: await response.json() }
  }
  try {
    assert.equal((await command('status', {}, 'wrong')).code, 401)
    assert.equal((await command('status')).body.bridge, 'ready')
    const list = await command('action-list')
    assert.equal(list.code, 200)
    assert.deepEqual(Object.keys(list.body.actions).sort(), ['computer_click', 'computer_foreground', 'input_type_text', 'os_notify', 'os_wifi_status', 'vision_screenshot'])
    assert.equal((await command('action-execute', { action: 'os_delete' })).code, 403)
    assert.equal((await command('action-execute', { action: 'macro_run' })).code, 403)
    assert.equal((await command('action-execute', { action: 'os_notify', params: { confirm: true } })).code, 403)
    assert.equal((await command('action-execute', { action: 'computer_click', params: { confirm: true } })).code, 403)
    assert.equal((await command('action-execute', { action: 'vision_screenshot', params: { path: 'C:\\windows\\test.png' } })).code, 403)
    const executed = await command('action-execute', { action: 'os_wifi_status' })
    assert.equal(executed.body.result.verificado, true)
    assert.equal((await command('action-execute', { action: 'computer_click', params: { x: 10, y: 10, expected_hwnd: 123 } })).code, 200)
    const audit = readFileSync(join(root, 'audit.jsonl'), 'utf8').trim().split('\n').map(line => JSON.parse(line))
    assert.deepEqual(audit.map(entry => [entry.action, entry.outcome]), [['computer_click', 'requested'], ['computer_click', 'success']])
    assert.equal((await command('lab-v1-snapshot')).body.success, true)
    assert.equal((await command('memory-user-search', { query: 'Alex' })).body.success, true)
    assert.equal((await command('memory-user-search', { query: '' })).code, 400)
    assert.equal((await command('project-memory-context')).body.success, true)
    assert.equal((await command('send-message', { message: 'hello' })).code, 403)
    assert.equal(calls.filter(call => call.type === 'action-execute').length, 2)
  } finally {
    await bridge.close()
    const absolute = resolve(root)
    assert.ok(absolute.startsWith(resolve(tmpdir()) + sep) && absolute.includes('zara-zoe-bridge-'))
    rmSync(absolute, { recursive: true, force: true })
  }
})
