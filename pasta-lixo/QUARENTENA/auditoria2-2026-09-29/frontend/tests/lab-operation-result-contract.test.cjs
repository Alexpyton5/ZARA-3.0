const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const root = path.join(__dirname, '..')
const main = fs.readFileSync(path.join(root, 'src/main.ts'), 'utf8')
const preload = fs.readFileSync(path.join(root, 'src/preload.ts'), 'utf8')
const hook = fs.readFileSync(path.join(root, 'src/renderer/components/zara-lab-v2/useLabRoom.ts'), 'utf8')
const styles = fs.readFileSync(path.join(root, 'src/renderer/components/zara-lab-v2/lab-room.css'), 'utf8')

test('terminal Lab result is forwarded, exposed and consumed with deduplication', () => {
  assert.match(main, /case 'lab-v1-operation-result'/)
  assert.match(main, /webContents\.send\('lab-v1-operation-result', msg\.data \|\| msg\)/)
  assert.match(preload, /labOperationResult:/)
  assert.match(preload, /ipcRenderer\.on\('lab-v1-operation-result'/)
  assert.match(hook, /seenOperationEvents/)
  assert.match(hook, /event\.event_id \|\| event\.operation_id/)
  assert.match(hook, /unsubscribe\?\.\(\)/)
})

test('both Lab submission entry points use the durable Main helper', () => {
  assert.match(main, /ipcMain\.handle\('lab-v1-submit', \(_event, payload\) => sendDurableLabOperation\(/)
  assert.match(main, /ipcMain\.handle\('lab-v1-autopilot', async \(_event, payload\) => \{/)
  assert.match(main, /const result = await sendDurableLabOperation\(/)
  assert.doesNotMatch(main, /lab-v1-autopilot'[\s\S]{0,500}sendToPython\('lab-v1-autopilot'/)
})

test('unknown durable confirmation tells the owner the same operation is retained', () => {
  const helper = main.slice(main.indexOf('async function sendDurableLabOperation'))
  assert.match(helper, /confirmationRecord\?\.confirmed !== true/)
  assert.match(helper, /confirmationRecord\?\.error/)
  assert.match(helper, /operationId.*preservada para retomada/s)
  assert.match(helper, /não reenvie a mensagem/)
})

test('Lab snapshot refreshes are coalesced instead of duplicating IPC reads', () => {
  assert.match(hook, /const pendingRead = useRef<Promise<void> \| null>\(null\)/)
  assert.match(hook, /const refreshQueued = useRef\(false\)/)
  assert.match(hook, /if \(pendingRead\.current\) \{\s*refreshQueued\.current = true/)
  assert.match(hook, /pendingRead\.current = request/)
  assert.match(hook, /if \(refreshQueued\.current\) \{[\s\S]*?void refresh\(\)/)
  assert.match(hook, /refreshQueued\.current = false; clearInterval\(interval\)/)
  assert.equal((hook.match(/setInterval\(/g) || []).length, 1)
})

test('Lab room styles preserve keyboard focus and motion preferences', () => {
  assert.match(styles, /:where\(button,input,textarea,select,summary\):focus-visible/)
  assert.match(styles, /overscroll-behavior:contain/)
  assert.match(styles, /prefers-reduced-motion:no-preference/)
  assert.match(styles, /prefers-contrast:more/)
  assert.match(styles, /forced-colors:active/)
})
