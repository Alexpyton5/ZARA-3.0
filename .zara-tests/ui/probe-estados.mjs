// Prova o comportamento dos estados do Core no DOM.
//
// Três coisas:
// 1. Todo estado que o backend REALMENTE emite chega ao `data-state` do Core.
// 2. SUCCESS e ERROR são momentâneos — se o STANDBY seguinte não chegar, o
//    Core volta sozinho ao repouso em vez de ficar verde ou vermelho.
// 3. Uma sequência rápida de fases (entendi -> executando -> conferindo ->
//    sucesso), que no backend leva milissegundos, aparece INTEIRA na tela.
//    Sem isso o Alex nunca vê que houve verificação.
//
// uso: node probe-estados.mjs <url>
import { createRequire } from 'node:module';
const { chromium } = createRequire(import.meta.url)('/opt/node22/lib/node_modules/playwright');

const [, , url] = process.argv;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1680, height: 980 } });

await page.addInitScript(() => {
  window.__vistos = [];
  window.zaraIPC = {
    system: { metrics: async () => ({ cpu: 10, ram: 20, disk: 30 }), info: async () => ({}), selfStatus: async () => ({}) },
    message: { send: async () => ({ response: 'ok' }), interrupt: async () => ({}) },
    voice: { start: async () => ({}), stop: async () => ({}), sendMicChunk: () => {} },
    action: { execute: async () => ({ result: { success: true, data: {} } }) },
    on: {
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
function checar(nome, real, esperado) {
  const ok = real === esperado;
  if (!ok) falhas += 1;
  console.log(`${ok ? 'OK ' : 'FALHOU'} ${nome}: ${JSON.stringify(real)} (esperado ${JSON.stringify(esperado)})`);
}

async function emitir(bruto, esperado, espera = 420) {
  await page.evaluate((s) => window.__estado?.(s), bruto);
  await page.waitForTimeout(espera);
  checar(String(bruto).padEnd(24), await page.getAttribute('.zh-core', 'data-state'), esperado);
}

// Exatamente os valores que core/ipc_handlers.py emite hoje
await emitir('LISTENING', 'listening');
await emitir('THINKING', 'thinking');
await emitir('UNDERSTANDING', 'understanding');
await emitir('EXECUTING', 'executing');
await emitir('VERIFYING', 'verifying');
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
checar('SUCCESS volta ao repouso sozinho', await page.getAttribute('.zh-core', 'data-state'), 'idle');
await emitir('ERROR', 'error');
await page.waitForTimeout(2900);
checar('ERROR volta ao repouso sozinho', await page.getAttribute('.zh-core', 'data-state'), 'idle');

// Sequência real de um comando de PC, disparada de uma vez só (é assim que
// o backend emite: as quatro fases em poucos milissegundos).
await page.evaluate(() => {
  window.__vistos = [];
  const alvo = document.querySelector('.zh-core');
  const obs = new MutationObserver(() => {
    const s = alvo.getAttribute('data-state');
    if (window.__vistos[window.__vistos.length - 1] !== s) window.__vistos.push(s);
  });
  obs.observe(alvo, { attributes: true, attributeFilter: ['data-state'] });
  window.__estado('UNDERSTANDING');
  window.__estado('EXECUTING');
  window.__estado('VERIFYING');
  window.__estado('SUCCESS');
});
await page.waitForTimeout(1600);
const vistos = await page.evaluate(() => window.__vistos);
checar('as 4 fases aparecem na ordem', JSON.stringify(vistos),
  JSON.stringify(['understanding', 'executing', 'verifying', 'success']));

console.log(falhas === 0 ? '\nEstados do Core conferem.' : `\n${falhas} verificação(ões) falharam.`);
await browser.close();
process.exit(falhas === 0 ? 0 : 1);
