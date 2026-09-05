// Prova que a Home não mostra dado inventado.
//
// Roda a mesma tela duas vezes: uma com backend que TEM dados, outra com
// backend vazio. Em nenhuma das duas pode aparecer o conteúdo de maquete que
// existia antes ("João espera sua resposta", "Reunião às 14:00", "61%",
// contagens 12/3/5/7 dos canais). E com backend vazio a tela tem que dizer
// que não há nada, em vez de preencher com exemplo.
//
// uso: node probe-sem-mentira.mjs <url> <dir-de-saida>
import { createRequire } from 'node:module';
const { chromium } = createRequire(import.meta.url)('/opt/node22/lib/node_modules/playwright');

const [, , url, outDir = '/tmp'] = process.argv;

// Tudo que era maquete e não pode voltar a aparecer.
const FICCAO = [
  'João espera sua resposta',
  'WhatsApp • 10 min',
  'Reunião às 14:00',
  '3 tarefas pendentes',
  'Atualização disponível',
  'Última sessão: hoje, 14:12',
  '61%',
];

const browser = await chromium.launch();
let falhas = 0;

async function rodar(nome, comDados) {
  const page = await browser.newPage({ viewport: { width: 1680, height: 980 } });
  await page.addInitScript((cheio) => {
    const agora = Date.now();
    window.zaraIPC = {
      system: { metrics: async () => ({ cpu: 11, ram: 22, disk: 33 }), info: async () => ({}), selfStatus: async () => ({}) },
      message: { send: async () => ({ response: 'ok' }), interrupt: async () => ({}) },
      voice: { start: async () => ({}), stop: async () => ({}), sendMicChunk: () => {} },
      action: { execute: async () => ({ result: { success: true, data: {} } }) },
      reminders: {
        list: async () => ({ success: true, reminders: cheio
          ? [{ id: 'r1', message: 'LEMBRETE_REAL_DO_BACKEND', due_at_utc: agora + 7200000, state: 'PENDING', source: 'voz' },
             { id: 'r2', message: 'outro', due_at_utc: agora + 9000000, state: 'PENDING', source: 'voz' }]
          : [] }),
      },
      conversationHistory: { list: async () => ({ messages: [], count: cheio ? 42 : 0, local_only: true }) },
      userMemory: { list: async () => ({ success: true, facts: cheio ? [{ id: 'f1' }, { id: 'f2' }, { id: 'f3' }] : [] }) },
      projectMemory: {
        list: async () => ({ success: true, keys: cheio ? ['doc_real'] : [] }),
        get: async () => ({ success: true, doc: { title: 'PROJETO_REAL_DO_BACKEND', content: 'x', updated_at: agora / 1000 } }),
      },
      on: {
        stateChange: () => () => {}, metrics: () => () => {}, message: () => () => {},
        voiceLevel: () => () => {}, voiceOutputAudio: () => () => {},
        reminderCreated: () => () => {}, reminderFired: () => () => {},
      },
    };
  }, comDados);

  await page.goto(url, { waitUntil: 'load' });
  await page.waitForTimeout(2200);
  const texto = (await page.textContent('.zh-content')) ?? '';

  for (const frase of FICCAO) {
    if (texto.includes(frase)) { falhas += 1; console.log(`FALHOU ${nome}: ficção na tela -> "${frase}"`); }
  }

  const esperados = comDados
    ? ['LEMBRETE_REAL_DO_BACKEND', '2 lembretes pendentes', '42 mensagens no histórico', '3 fatos na memória', 'PROJETO_REAL_DO_BACKEND']
    : ['Nada pendente agora.', 'Nenhum projeto ativo'];

  for (const esperado of esperados) {
    const ok = texto.includes(esperado);
    if (!ok) falhas += 1;
    console.log(`${ok ? 'OK ' : 'FALHOU'} ${nome}: "${esperado}"`);
  }

  // Os canais de comunicação não podem exibir contagem nenhuma.
  const contagens = await page.$$eval('.zh-comm-value', (els) => els.map((e) => e.textContent?.trim()));
  const limpos = contagens.every((c) => c === '—');
  if (!limpos) falhas += 1;
  console.log(`${limpos ? 'OK ' : 'FALHOU'} ${nome}: canais sem contagem inventada -> ${JSON.stringify(contagens)}`);

  await page.screenshot({ path: `${outDir}/home-${comDados ? 'com-dados' : 'vazia'}.png` });
  await page.close();
}

await rodar('com dados ', true);
await rodar('sem dados ', false);

console.log(falhas === 0 ? '\nNenhum dado inventado na Home.' : `\n${falhas} verificação(ões) falharam.`);
await browser.close();
process.exit(falhas === 0 ? 0 : 1);
