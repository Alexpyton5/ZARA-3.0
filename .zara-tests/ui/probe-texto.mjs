// Prova que o comando de TEXTO tem volta na tela.
//
// Antes desta tira, `message.send` era chamado e a resposta era descartada:
// o Alex digitava e não via nada. Aqui o stub responde no MESMO formato de
// `handle_send_message` (`{response, engine}`) e o teste confere que a
// resposta REAL do backend aparece no DOM — e que uma falha aparece como
// falha, não como silêncio.
//
// uso: node probe-texto.mjs <url> <dir-de-saida>
import { createRequire } from 'node:module';
const { chromium } = createRequire(import.meta.url)('/opt/node22/lib/node_modules/playwright');

const [, , url, outDir = '/tmp'] = process.argv;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1680, height: 980 } });

await page.addInitScript(() => {
  window.__enviados = [];
  window.zaraIPC = {
    system: { metrics: async () => ({ cpu: 12, ram: 40, disk: 55 }), info: async () => ({}), selfStatus: async () => ({}) },
    message: {
      send: async ({ message }) => {
        window.__enviados.push(message);
        if (message.includes('quebrar')) throw new Error('sidecar fora do ar');
        if (message.includes('mudo')) return { engine: 'auto' }; // sem `response`
        return { response: `RESPOSTA_REAL_DO_BACKEND para "${message}"`, engine: 'gemini' };
      },
      interrupt: async () => ({}),
    },
    voice: { start: async () => ({}), stop: async () => ({}), sendMicChunk: () => {} },
    action: { execute: async () => ({ result: { success: true, data: {} } }) },
    on: {
      stateChange: () => () => {},
      metrics: () => () => {},
      // caminho de VOZ: guardamos o callback para disparar um evento depois
      message: (cb) => { window.__msgCb = cb; return () => {}; },
      voiceLevel: () => () => {}, voiceOutputAudio: () => () => {},
      reminderCreated: () => () => {}, reminderFired: () => () => {},
    },
  };
});

await page.goto(url, { waitUntil: 'load' });
await page.waitForTimeout(2000);

let falhas = 0;
async function checar(nome, esperado) {
  await page.waitForTimeout(700);
  const texto = (await page.textContent('.zh-strip')) ?? '';
  const ok = texto.includes(esperado);
  if (!ok) falhas += 1;
  console.log(`${ok ? 'OK ' : 'FALHOU'} ${nome}: esperava "${esperado}"`);
  return texto;
}

// 1. texto normal -> a resposta do backend aparece
await page.fill('.zh-command-input', 'que horas sao');
await page.press('.zh-command-input', 'Enter');
await checar('resposta de texto aparece', 'RESPOSTA_REAL_DO_BACKEND para "que horas sao"');
await checar('a fala do Alex aparece', 'que horas sao');

// 2. backend responde sem texto -> a tela diz isso, nao finge sucesso
await page.fill('.zh-command-input', 'fica mudo');
await page.press('.zh-command-input', 'Enter');
await checar('resposta vazia vira aviso', 'não devolveu resposta');

// 3. erro de IPC -> aparece como erro
await page.fill('.zh-command-input', 'vai quebrar');
await page.press('.zh-command-input', 'Enter');
await checar('erro de IPC aparece', 'sidecar fora do ar');

// 4. caminho de VOZ: evento `message` alimenta a mesma tira
await page.evaluate(() => window.__msgCb?.({ role: 'assistant', content: 'FALA_VINDA_DA_VOZ', engine: 'gemini_live' }));
await checar('evento de voz usa a mesma tira', 'FALA_VINDA_DA_VOZ');

await page.screenshot({ path: `${outDir}/texto-strip.png` });
console.log(falhas === 0 ? '\nTexto e voz têm volta na tela.' : `\n${falhas} verificação(ões) falharam.`);
await browser.close();
process.exit(falhas === 0 ? 0 : 1);
