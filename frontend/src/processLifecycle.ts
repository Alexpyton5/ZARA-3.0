import { spawn, type ChildProcess, type SpawnOptions } from 'child_process'
import { realpathSync } from 'fs'
import { join, resolve } from 'path'

export interface OwnedChildProcess {
  child: ChildProcess
  pid: number
  executablePath: string
}

function normalizedPath(path: string): string {
  let normalized = resolve(path)
  try {
    normalized = realpathSync.native(normalized)
  } catch {
    // The packaged executable can disappear during an uninstall race.  The
    // resolved path is still useful, while process identity remains mandatory.
  }
  return process.platform === 'win32' ? normalized.toLocaleLowerCase('en-US') : normalized
}

function windowsSystemExecutable(name: string): string {
  const windowsRoot = process.env.SystemRoot || process.env.WINDIR
  return windowsRoot ? join(windowsRoot, 'System32', name) : name
}

export function captureOwnedChild(child: ChildProcess, executablePath: string): OwnedChildProcess {
  const pid = child.pid
  if (!Number.isSafeInteger(pid) || Number(pid) <= 0) {
    throw new Error('Spawned child has no valid PID')
  }
  return { child, pid: Number(pid), executablePath: normalizedPath(executablePath) }
}

export function isOwnedChildLive(owned: OwnedChildProcess): boolean {
  return owned.child.pid === owned.pid
    && owned.child.exitCode === null
    && owned.child.signalCode === null
}

function collectOutput(
  command: string,
  args: string[],
  options: SpawnOptions,
  timeoutMs: number,
): Promise<{ code: number | null; stdout: string }> {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(command, args, { ...options, shell: false })
    let stdout = ''
    let settled = false
    let timer: ReturnType<typeof setTimeout> | null = null
    const finish = (result: { code: number | null; stdout: string }) => {
      if (settled) return
      settled = true
      if (timer) clearTimeout(timer)
      resolvePromise(result)
    }
    child.stdout?.on('data', (chunk) => { stdout += chunk.toString() })
    child.once('error', (error) => {
      if (settled) return
      settled = true
      if (timer) clearTimeout(timer)
      reject(error)
    })
    child.once('exit', (code) => finish({ code, stdout }))
    timer = setTimeout(() => {
      if (settled) return
      child.kill()
      finish({ code: null, stdout })
    }, timeoutMs)
  })
}

async function inspectWindowsExecutable(pid: number): Promise<string | null> {
  const script = [
    `$p = Get-Process -Id ${pid} -ErrorAction Stop`,
    '[Console]::Out.Write($p.Path)',
  ].join('; ')
  try {
    const result = await collectOutput(
      windowsSystemExecutable('WindowsPowerShell\\v1.0\\powershell.exe'),
      ['-NoLogo', '-NoProfile', '-NonInteractive', '-Command', script],
      { windowsHide: true, stdio: ['ignore', 'pipe', 'ignore'] },
      3000,
    )
    if (result.code !== 0 || !result.stdout.trim()) return null
    return normalizedPath(result.stdout.trim())
  } catch {
    return null
  }
}

async function runWindowsTreeKill(pid: number): Promise<boolean> {
  try {
    const result = await collectOutput(
      windowsSystemExecutable('taskkill.exe'),
      ['/PID', String(pid), '/T', '/F'],
      { windowsHide: true, stdio: ['ignore', 'ignore', 'ignore'] },
      5000,
    )
    return result.code === 0
  } catch {
    return false
  }
}

/**
 * Terminate only the still-live process captured from our own spawn call.
 *
 * PyInstaller onefile uses a bootloader parent plus the real Python child, so
 * Windows must terminate the exact owned tree rather than calling ChildProcess
 * kill() on only the bootloader PID.
 */
export async function terminateOwnedProcessTree(owned: OwnedChildProcess): Promise<boolean> {
  if (!isOwnedChildLive(owned)) return true

  if (process.platform === 'win32') {
    const observedPath = await inspectWindowsExecutable(owned.pid)
    if (!observedPath || observedPath !== owned.executablePath || !isOwnedChildLive(owned)) {
      return false
    }
    return runWindowsTreeKill(owned.pid)
  }

  // Development on POSIX launches Python directly, with no onefile bootloader.
  return owned.child.kill('SIGTERM')
}
