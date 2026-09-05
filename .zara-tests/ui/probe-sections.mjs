// Harness das seções da Sidebar. Injeta um `window.zaraIPC` com o MESMO
// formato que os handlers de core/ipc_handlers.py respondem (conferido em
// handle_conversation_history_list, handle_memory_user_list,
// handle_reminder_list, handle_project_memory_list, handle_self_status e a
// action os_app_list), clica cada item da Sidebar e prova que a tela mudou.
//
// uso: node probe-sections.mjs <url> <dir-de-saida>
import { createRequire } from 'node:module';
const { chromium } = createRequire(import.meta.url)('/opt/node22/lib/node_modules/playwright');

const [, , url, outDir = '/tmp'] = process.argv;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1680, height: 980 } });

await page.addInitScript(() => {
  const now = Date.now();
  window.zaraIPC = {
    system: {
      metrics: async () => ({ cpu: 37.5, ram: 62.4, disk: 71.8, netUp: 0, netDown: 0 }),
      info: async () => ({}),
      selfStatus: async () => ({
        capabilities: [
          { label: 'VOLUME/MUTE', status: 'AVAILABLE', detail: 'controle com verificação de volume' },
          { label: 'BRILHO', status: 'UNSUPPORTED', detail: 'depende do monitor expor DDC/CI ou WMI' },
          { label: 'MEMÓRIA', status: 'LIMITED', detail: 'User Memory e Project Memory separadas' },
          { label: 'VOZ', status: 'OFFLINE', detail: 'pipeline não preparado' },
        ],
      }),
    },
    conversationHistory: {
      list: async () => ({
        messages: [
          { id: 'm1', role: 'user', content: 'Zara, que horas são?', engine: '', timestamp: now - 60000 },
          { id: 'm2', role: 'assistant', content: 'São 03:41.', engine: 'gemini', timestamp: now - 59000 },
        ],
        count: 2,
        local_only: true,
      }),
      clear: async () => ({ deleted: 2 }),
    },
    userMemory: {
      list: async () => ({
        success: true,
        facts: [
          { id: 'f1', fact: 'Prefere respostas curtas', category: 'preferencia', confidence: 0.9, status: 'active', source: 'conversa', updated_at: now / 1000 },
        ],
      }),
      forget: async () => ({ success: true }),
    },
    projectMemory: {
      list: async () => ({ success: true, keys: ['arquitetura', 'roadmap'] }),
      get: async (k) => ({ success: true, doc: { title: `Doc ${k}`, content: 'conteudo real do doc' } }),
    },
    reminders: {
      list: async () => ({ success: true, reminders: [{ id: 'r1', message: 'Reunião 14h', due_at_utc: now + 3600000, state: 'PENDING', source: 'voz' }] }),
      cancel: async () => ({ success: true }),
    },
    lab: { state: async () => ({ proposals: [], messages: [] }) },
    message: { send: async () => ({}), interrupt: async () => ({}) },
    voice: { start: async () => ({}), stop: async () => ({}), sendMicChunk: () => {} },
    action: {
      execute: async (name) => {
        if (name === 'os_app_list') {
          return { result: { success: true, data: { platform_supported: false, count: 3, apps: [
            { id: 'chrome', display_name: 'Chrome', aliases: [], installed: null, running: null },
            { id: 'vs_code', display_name: 'VS Code', aliases: ['vs code', 'vscode'], installed: null, running: null },
            { id: 'figma', display_name: 'Figma', aliases: ['figma'], installed: null, running: null },
          ] } } };
        }
        return { result: { success: true, data: { count: 128 } } };
      },
    },
    on: {
      stateChange: () => () => {}, metrics: () => () => {}, message: () => () => {},
      voiceLevel: () => () => {}, voiceOutputAudio: () => () => {},
      reminderCreated: () => () => {}, reminderFired: () => () => {},
    },
  };
});

await page.goto(url, { waitUntil: 'load' });
await page.waitForTimeout(2500);

const secoes = ['Conversas', 'Projetos', 'Arquivos', 'Aplicativos', 'Automações', 'Memórias', 'ZARA Lab', 'Dispositivos', 'Sistema', 'Configurações', 'Hoje'];
let falhas = 0;

for (const nome of secoes) {
  await page.click(`.zh-nav-item:has-text("${nome}")`);
  await page.waitForTimeout(900);
  const visto = await page.evaluate(() => {
    const sec = document.querySelector('.zh-section-view');
    return {
      titulo: sec?.querySelector('h1')?.textContent ?? null,
      corpo: (sec?.querySelector('.zh-section-view-body')?.textContent ?? '').replace(/\s+/g, ' ').trim().slice(0, 110),
      home: Boolean(document.querySelector('.zh-content-top')),
      sistema: Boolean(document.querySelector('.zh-system-row')),
    };
  });
  const mudou = visto.titulo !== null || visto.home || visto.sistema;
  if (!mudou) falhas += 1;
  console.log(`${mudou ? 'OK ' : 'FALHOU'} ${nome.padEnd(14)} titulo=${visto.titulo ?? (visto.home ? '(Home)' : visto.sistema ? '(Sistema)' : 'NADA')} | ${visto.corpo}`);
  await page.screenshot({ path: `${outDir}/sec-${nome.replace(/\s/g, '_')}.png` });
}

console.log(falhas === 0 ? '\nTodas as seções renderaram algo real.' : `\n${falhas} seção(ões) não renderaram nada.`);
await browser.close();
process.exit(falhas === 0 ? 0 : 1);
