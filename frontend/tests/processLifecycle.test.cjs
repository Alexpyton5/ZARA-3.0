const assert = require('node:assert/strict')
const { spawn, spawnSync } = require('node:child_process')
const { once } = require('node:events')
const test = require('node:test')

const {
  captureOwnedChild,
  isOwnedChildLive,
  terminateOwnedProcessTree,
} = require('../dist-electron/processLifecycle.js')

function pidExists(pid) {
  try {
    process.kill(pid, 0)
    return true
  } catch {
    return false
  }
}

async function firstLine(stream) {
  let buffered = ''
  for await (const chunk of stream) {
    buffered += chunk.toString()
    const newline = buffered.indexOf('\n')
    if (newline >= 0) return buffered.slice(0, newline).trim()
  }
  throw new Error('child did not publish its descendant PID')
}

test('capture retains exact child PID and executable path', () => {
  const child = spawn(process.execPath, ['-e', 'setTimeout(() => {}, 30000)'])
  try {
    const owned = captureOwnedChild(child, process.execPath)
    assert.equal(owned.pid, child.pid)
    assert.match(owned.executablePath.toLowerCase(), /node\.exe$/)
    assert.equal(isOwnedChildLive(owned), true)
  } finally {
    child.kill()
  }
})

test('Windows termination stops only the exact owned root and its descendants', {
  skip: process.platform !== 'win32',
}, async () => {
  const descendantCode = 'setInterval(() => {}, 30000)'
  const rootCode = [
    "const { spawn } = require('node:child_process')",
    `const child = spawn(process.execPath, ['-e', ${JSON.stringify(descendantCode)}])`,
    'console.log(child.pid)',
    'setInterval(() => {}, 30000)',
  ].join('; ')
  const root = spawn(process.execPath, ['-e', rootCode], {
    stdio: ['ignore', 'pipe', 'ignore'],
    windowsHide: true,
  })
  const owned = captureOwnedChild(root, process.execPath)
  let descendantPid = 0
  try {
    descendantPid = Number(await firstLine(root.stdout))
    assert.ok(Number.isSafeInteger(descendantPid) && descendantPid > 0)

    assert.equal(await terminateOwnedProcessTree(owned), true)
    if (root.exitCode === null && root.signalCode === null) await once(root, 'exit')

    assert.equal(pidExists(owned.pid), false)
    assert.equal(pidExists(descendantPid), false)
  } finally {
    if (pidExists(owned.pid)) {
      spawnSync('taskkill.exe', ['/PID', String(owned.pid), '/T', '/F'], {
        stdio: 'ignore',
        windowsHide: true,
      })
    }
  }
})

