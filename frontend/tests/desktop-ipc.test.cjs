// Executes the actual main/preload code against Electron and OS fakes.
// No browser, process, microphone or real filesystem write is permitted.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function harness({ installed = [], openError = '' } = {}) {
  const handlers = new Map();
  const opened = [];
  const processFake = {
    env: { LOCALAPPDATA: 'C:/Sandbox/Local', ProgramFiles: 'C:/Programs' },
    argv: [], platform: 'win32', stdout: { on() {} }, stderr: { on() {} }, on() {},
  };
  const electron = {
    app: { requestSingleInstanceLock: () => true, on() {}, whenReady: () => new Promise(() => {}),
      getPath: (id) => path.join('C:/Sandbox', id) },
    ipcMain: { handle: (name, handler) => handlers.set(name, handler), on() {} },
    shell: { openExternal: async value => { opened.push(value); },
      openPath: async value => { opened.push(value); return openError; } },
  };
  const fakes = {
    electron,
    fs: { existsSync: p => installed.includes(p), readdirSync: () => [], writeFileSync: () => assert.fail('write') },
    path,
    child_process: { spawn: () => assert.fail('spawn'), execFileSync: () => assert.fail('exec') },
    './reminderEvents': { normalizeReminderEvent: value => value },
  };
  const code = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/main.ts'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  vm.runInNewContext(code + '\nsetupIPC();', {
    require: name => { if (!Object.hasOwn(fakes, name)) assert.fail(name); return fakes[name]; },
    exports: {}, process: processFake, console, setTimeout, clearTimeout, __dirname,
  });
  return { handlers, opened, invoke: (channel, value) => handlers.get(channel)({}, value) };
}

test('unknown IDs cannot open paths, URLs or settings, including prototype keys', async () => {
  const h = harness();
  for (const channel of ['desktop-open-app', 'desktop-open-external', 'desktop-open-settings', 'desktop-open-folder']) {
    for (const value of ['__proto__', 'constructor', 'https://unknown.invalid', 'C:/Windows/cmd.exe', null, {}]) {
      assert.equal((await h.invoke(channel, value)).success, false);
    }
  }
  assert.deepEqual(h.opened, []);
});

test('service and Windows settings shortcuts open only their defined targets', async () => {
  const h = harness();
  assert.equal((await h.invoke('desktop-open-external', 'gmail')).success, true);
  assert.equal((await h.invoke('desktop-open-settings', 'startup')).success, true);
  assert.equal((await h.invoke('desktop-open-folder', 'downloads')).success, true);
  assert.deepEqual(h.opened, ['https://mail.google.com/', 'ms-settings:startupapps', path.join('C:/Sandbox', 'downloads')]);
});

test('installed app dispatch and absent app truth are distinct', async () => {
  const executable = path.join('C:/Sandbox/Local', 'Programs', 'Microsoft VS Code', 'Code.exe');
  const h = harness({ installed: [executable] });
  assert.equal((await h.invoke('desktop-open-app', 'vscode')).success, true);
  assert.equal((await h.invoke('desktop-open-app', 'docker')).success, false);
  assert.deepEqual(h.opened, [executable]);
});

test('shell launch errors propagate without a false success', async () => {
  const h = harness({ openError: 'Access denied' });
  const result = await h.invoke('desktop-open-folder', 'documents');
  assert.equal(result.success, false);
  assert.equal(result.error, 'Access denied');
});

test('preload shortcut bridge preserves semantic IDs', async () => {
  let api;
  const invoked = [];
  const code = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/preload.ts'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  vm.runInNewContext(code, { exports: {}, require: name => {
    assert.equal(name, 'electron');
    return { contextBridge: { exposeInMainWorld: (_name, exposed) => { api = exposed; } },
      ipcRenderer: { invoke: async (...args) => { invoked.push(args); return { success: true }; } } };
  } });
  await api.desktop.openApp('postman');
  await api.desktop.openExternal('whatsapp');
  await api.projectMemory.context();
  assert.deepEqual(invoked, [['desktop-open-app', 'postman'], ['desktop-open-external', 'whatsapp'], ['project-memory-context']]);
});
