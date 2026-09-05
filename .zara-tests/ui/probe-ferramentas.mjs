// Prova que o card Ferramentas não finge sucesso.
//
// O clique chamava `os_app` e descartava o resultado: app não instalado ou
// executor com erro davam exatamente a mesma tela de um sucesso. Aqui o stub
// responde no formato real do ActionResult e o teste confere que a falha
// aparece como falha e o sucesso mostra o texto DO EXECUTOR.
//
// uso: node probe-ferramentas.mjs <url>
import { createRequire } from 'node:module';
const { chromium } = createRequire(import.meta.url)('/opt/node22/lib/node_modules/playwright');

const [, , url] = process.argv;
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1680, height: 980 } });

await page.addInitScript(() => {
  window.zaraIPC = {
    system: { metrics: async () => ({ cpu: 1, ram: 2, disk: 3 }), info: async () => ({}), selfStatus: async () => ({}) },
    message: { send: async () => ({ response: 'ok' }), interrupt: async () => ({}) },
    voice: { start: async () => ({}), stop: async () => ({}), sendMicChunk: () => {} },
    action: {
      execute: async (nome, params) => {
        if (nome === 'os_app_list') {
          return { result: { success: true, data: { platform_supported: true, apps: [
            { id: 'vs_code', display_name: 'VS Code', aliases: [], installed: true, running: false },
            { id: 'figma', display_name: 'Figma', aliases: [], installed: false, running: false },
            { id: 'postman', display_name: 'Postman', aliases: [], installed: true, running: true },
            { id: 'docker', display_name: 'Docker', aliases: [], installed: true, running: false },
          ] } } };
        }
        if (nome === 'os_app' && params.app === 'vs_code') {
          return { result: { success: true, output: 'SAIDA_DO_EXECUTOR: VS Code aberto e verificado.' } };
        }
        if (nome === 'os_app' && params.app === 'docker') {
          return { result: { success: false, error: 'ERRO_DO_EXECUTOR: processo não verificado.' } };
        }
        return { result: { success: true, data: {} } };
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
await page.waitForTimeout(2200);

let falhas = 0;
async function ler(nome) {
  return page.evaluate((n) => {
    const tiles = [...document.querySelectorAll('.zh-tool-tile')];
    const t = tiles.find((e) => e.querySelector('.zh-tool-name')?.textContent === n);
    return { rotulo: t?.querySelector('.zh-tool-open')?.textContent ?? null, desabilitado: t?.disabled ?? null };
  }, nome);
}
function checar(nome, real, esperado) {
  const ok = real === esperado;
  if (!ok) falhas += 1;
  console.log(`${ok ? 'OK ' : 'FALHOU'} ${nome}: ${JSON.stringify(real)} (esperado ${JSON.stringify(esperado)})`);
}

// Estado inicial vem de os_app_list, não de texto fixo
checar('Postman rodando', (await ler('Postman')).rotulo, 'Aberto agora');
const figma = await ler('Figma');
checar('Figma não instalado', figma.rotulo, 'Não encontrado');
checar('Figma desabilitado', figma.desabilitado, true);
checar('VS Code disponível', (await ler('VS Code')).rotulo, 'Abrir');

// Sucesso: o texto vem do executor
await page.click('.zh-tool-tile:has(.zh-tool-name:text-is("VS Code"))');
await page.waitForTimeout(600);
checar('sucesso usa texto do executor', (await ler('VS Code')).rotulo, 'SAIDA_DO_EXECUTOR: VS Code aberto e verificado.');

// Falha: aparece como falha, não como sucesso silencioso
await page.click('.zh-tool-tile:has(.zh-tool-name:text-is("Docker"))');
await page.waitForTimeout(600);
checar('falha aparece como falha', (await ler('Docker')).rotulo, 'ERRO_DO_EXECUTOR: processo não verificado.');

console.log(falhas === 0 ? '\nFerramentas não finge sucesso.' : `\n${falhas} verificação(ões) falharam.`);
await browser.close();
process.exit(falhas === 0 ? 0 : 1);
