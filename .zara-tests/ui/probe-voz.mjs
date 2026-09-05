// Prova o estado do botão de voz do dock.
//
// O `listening` era só do renderer: reabrir a janela com a voz já ligada, ou
// o backend derrubar o pipeline sozinho, deixava o botão contando uma
// história própria. Aqui o stub controla `voice-status` e o estado do Core,
// e o teste confere o `data-listening` real no DOM.
//
// uso: node probe-voz.mjs <url> [listeningInicial]
import { createRequire } from 'node:module';
const { chromium } = createRequire(import.meta.url)('/opt/node22/lib/node_modules/playwright');

const [, , url] = process.argv;
const browser = await chromium.launch();
let falhas = 0;

function base(listeningInicial) {
  return (inicial) => {
    window.__estado = null;
    window.zaraIPC = {
      system: { metrics: async () => ({ cpu: 1, ram: 2, disk: 3 }), info: async () => ({}), selfStatus: async () => ({}) },
      message: { send: async () => ({ response: 'ok' }), interrupt: async () => ({}) },
      voice: {
        start: async () => ({}), stop: async () => ({}), sendMicChunk: () => {},
        status: async () => ({ listening: inicial, mode: 'gemini_live' }),
      },
      action: { execute: async () => ({ result: { success: true, data: {} } }) },
      on: {
        stateChange: (cb) => { window.__estado = cb; return () => {}; },
        metrics: () => () => {}, message: () => () => {},
        voiceLevel: () => () => {}, voiceOutputAudio: () => () => {},
        reminderCreated: () => () => {}, reminderFired: () => () => {},
      },
    };
    void listeningInicial;
  };
}

async function abrir(listeningInicial) {
  const page = await browser.newPage({ viewport: { width: 1680, height: 980 } });
  await page.addInitScript(base(listeningInicial), listeningInicial);
  await page.goto(url, { waitUntil: 'load' });
  await page.waitForTimeout(1800);
  return page;
}

function checar(nome, real, esperado) {
  const ok = real === esperado;
  if (!ok) falhas += 1;
  console.log(`${ok ? 'OK ' : 'FALHOU'} ${nome}: ${JSON.stringify(real)} (esperado ${JSON.stringify(esperado)})`);
}

// 1. backend diz que já está ouvindo -> o botão nasce ouvindo
{
  const page = await abrir(true);
  checar('nasce ouvindo quando o backend diz que está',
    await page.getAttribute('.zh-dock-voice', 'data-listening'), 'true');
  await page.close();
}

// 2. backend diz que não está -> o botão nasce parado
{
  const page = await abrir(false);
  checar('nasce parado quando o backend diz que não',
    await page.getAttribute('.zh-dock-voice', 'data-listening'), 'false');

  // 3. voz cai (Core offline) -> o botão não pode continuar dizendo "ouvindo"
  await page.evaluate(() => window.__estado?.('LISTENING'));
  await page.waitForTimeout(300);
  await page.evaluate(() => window.__estado?.('OFFLINE'));
  await page.waitForTimeout(400);
  checar('voz fora do ar zera o botão',
    await page.getAttribute('.zh-dock-voice', 'data-listening'), 'false');
  checar('voz fora do ar mostra o aviso',
    ((await page.textContent('.zh-core-column')) ?? '').includes('Voz não conectada'), true);
  await page.close();
}

console.log(falhas === 0 ? '\nBotão de voz segue o backend.' : `\n${falhas} verificação(ões) falharam.`);
await browser.close();
process.exit(falhas === 0 ? 0 : 1);
