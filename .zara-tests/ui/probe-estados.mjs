// Prova o comportamento dos estados do Core no DOM.
//
// Dois pontos: (1) todo estado que o backend REALMENTE emite chega ao
// `data-state` do Core; (2) SUCCESS e ERROR são momentâneos — se o STANDBY
// seguinte não chegar, o Core volta sozinho ao repouso em vez de ficar verde
// ou vermelho para sempre.
//
// uso: node probe-estados.mjs <url>
import { createRequire } from 'node:module';
const { chromium } = createRequire(import.meta.url)('/opt/node22/lib/node_modules/playwright');

const [, , url] = process.argv;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1680, height: 980 } });

await page.addInitScript(() => {
  window.zaraIPC = {
    system: { metrics: async () => ({ cpu: 10, ram: 20, disk: 30 }), info: async () => ({}), selfStatus: async () => ({}) },
    message: { send: async () => ({ response: 'ok' }), interrupt: async () => ({}) },
    voice: { start: async () => ({}), stop: async () => ({}), sendMicChunk: () => {} },
    action: { execute: async () => ({ result: { success: true, data: {} } }) },
    on: {
      // guardamos o callback para emitir estados como o backend emite
      stateChange: (cb) => { window.__estado = cb; return () => {}; },
      metrics: () => () => {}, message: () => () => {},
      voiceLevel: () => () => {}, voiceOutputAudio: () => () => {},
      reminderCreated: () => () => {}, reminderFired: () => () => {},
    },
  };
});

await page.goto(url, { waitUntil: 'load' });
await page.waitForTimeout(1800);

let falhas = 0;
async function emitir(bruto, esperado, espera = 320) {
  await page.evaluate((s) => window.__estado?.(s), bruto);
  await page.waitForTimeout(espera);
  const lido = await page.getAttribute('.zh-core', 'data-state');
  const ok = lido === esperado;
  if (!ok) falhas += 1;
  console.log(`${ok ? 'OK ' : 'FALHOU'} ${String(bruto).padEnd(24)} -> ${lido} (esperado ${esperado})`);
}

// Exatamente os valores que core/ipc_handlers.py emite hoje
await emitir('LISTENING', 'listening');
await emitir('THINKING', 'thinking');
await emitir('EXECUTING', 'executing');
await emitir('SPEAKING', 'speaking');
await emitir('STANDBY', 'idle');
// Estado emitido pelo processo principal no gate HIGH
await emitir('AWAITING_AUTHORIZATION', 'awaiting_authorization');
await emitir('STANDBY', 'idle');
// Valor desconhecido não pode quebrar a UI
await emitir('QUALQUER_COISA', 'idle');

// SUCCESS e ERROR são momentâneos e voltam sozinhos
await emitir('SUCCESS', 'success');
await page.waitForTimeout(2900);
{
  const lido = await page.getAttribute('.zh-core', 'data-state');
  const ok = lido === 'idle';
  if (!ok) falhas += 1;
  console.log(`${ok ? 'OK ' : 'FALHOU'} SUCCESS volta ao repouso sozinho -> ${lido}`);
}
await emitir('ERROR', 'error');
await page.waitForTimeout(2900);
{
  const lido = await page.getAttribute('.zh-core', 'data-state');
  const ok = lido === 'idle';
  if (!ok) falhas += 1;
  console.log(`${ok ? 'OK ' : 'FALHOU'} ERROR volta ao repouso sozinho -> ${lido}`);
}

console.log(falhas === 0 ? '\nEstados do Core conferem.' : `\n${falhas} verificação(ões) falharam.`);
await browser.close();
process.exit(falhas === 0 ? 0 : 1);
