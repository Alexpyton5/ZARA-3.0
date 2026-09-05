// Harness de verificação da Home: injeta um `window.zaraIPC` com o MESMO
// formato que o backend Python responde de verdade, renderiza a Home no
// Chromium e tira o print. Serve para provar que a UI lê o contrato real,
// sem depender do Windows nem do sidecar.
//
// uso: node probe.mjs <url> <arquivo.png> [estadoDoCore]
import { createRequire } from 'node:module';
const { chromium } = createRequire(import.meta.url)('/opt/node22/lib/node_modules/playwright');

const [, , url, out, coreState = 'idle'] = process.argv;

// Formato REAL de core/ipc_handlers.py -> handle_system_metrics
const METRICS = { cpu: 37.5, ram: 62.4, disk: 71.8, netUp: 0, netDown: 0 };

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1680, height: 980 } });

await page.addInitScript(
  ({ metrics, coreState }) => {
    const listeners = {};
    window.zaraIPC = {
      system: {
        metrics: async () => metrics,
        info: async () => ({}),
        selfStatus: async () => ({ capabilities: [{ status: 'AVAILABLE' }, { status: 'UNAVAILABLE' }] }),
      },
      message: { send: async () => ({}), interrupt: async () => ({}) },
      voice: { start: async () => ({}), stop: async () => ({}), sendMicChunk: () => {} },
      action: { execute: async () => ({ result: { success: true, data: { count: 128 } } }) },
      on: {
        stateChange: (cb) => { listeners.state = cb; setTimeout(() => cb(coreState), 300); return () => {}; },
        metrics: () => () => {},
        message: () => () => {},
        voiceLevel: () => () => {},
        voiceOutputAudio: () => () => {},
        reminderCreated: () => () => {},
        reminderFired: () => () => {},
      },
    };
  },
  { metrics: METRICS, coreState },
);

await page.goto(url, { waitUntil: 'load' });
await page.waitForTimeout(3500);

// Lê o que o painel de Sistema realmente mostrou, não o que eu espero
const lidos = await page.evaluate(() => {
  const linhas = [...document.querySelectorAll('.zh-metric-row')];
  return linhas.map((l) => l.textContent.replace(/\s+/g, ' ').trim());
});
const estado = await page.getAttribute('.zh-core', 'data-state');

console.log('estado do Core no DOM:', estado);
console.log('linhas de métrica renderizadas:');
lidos.forEach((l) => console.log('   ', l));

await page.screenshot({ path: out });
await browser.close();
