// Prova que os cards do painel Sistema que passaram a ter backend fazem
// leitura REAL — e que a resposta do executor é o que aparece na tela.
//
// Regra que está sendo prendida: nada de string fixa de sucesso. Se a action
// falhar, o card mostra o erro DO EXECUTOR, não "Indisponível" genérico nem
// um texto simpático inventado no renderer.
//
// uso: node probe-sistema.mjs <url>
import { createRequire } from 'node:module';
const { chromium } = createRequire(import.meta.url)('/opt/node22/lib/node_modules/playwright');

const [, , url] = process.argv;
const browser = await chromium.launch();
let falhas = 0;

function checar(nome, real, esperado) {
  const ok = real === esperado;
  if (!ok) falhas += 1;
  console.log(`${ok ? 'OK ' : 'FALHOU'} ${nome}: ${JSON.stringify(real)} (esperado ${JSON.stringify(esperado)})`);
}

async function abrir(respostas) {
  const page = await browser.newPage({ viewport: { width: 1680, height: 980 } });
  await page.addInitScript((r) => {
    window.zaraIPC = {
      system: {
        metrics: async () => ({ cpu: 1, ram: 2, disk: 3 }),
        info: async () => ({}),
        selfStatus: async () => ({ capabilities: [{ status: 'AVAILABLE' }, { status: 'AVAILABLE' }, { status: 'OFFLINE' }] }),
      },
      userMemory: { list: async () => ({ success: true, facts: [] }) },
      message: { send: async () => ({ response: 'ok' }), interrupt: async () => ({}) },
      voice: { start: async () => ({}), stop: async () => ({}), sendMicChunk: () => {} },
      action: { execute: async (nome) => r[nome] ?? { result: { success: true, data: {} } } },
      on: {
        stateChange: () => () => {}, metrics: () => () => {}, message: () => () => {},
        voiceLevel: () => () => {}, voiceOutputAudio: () => () => {},
        reminderCreated: () => () => {}, reminderFired: () => () => {},
      },
    };
  }, respostas);
  await page.goto(url, { waitUntil: 'load' });
  await page.waitForTimeout(1800);
  return page;
}

async function sub(page, label) {
  return page.evaluate((l) => {
    const cards = [...document.querySelectorAll('.zh-action-card, .zh-action-row, .zh-action-row--btn')];
    const alvo = cards.find((c) => (c.querySelector('strong, .zh-action-label')?.textContent ?? '') === l);
    return alvo?.querySelector('.zh-action-card-text span:last-child, .zh-action-sub')?.textContent ?? null;
  }, label);
}

async function clicar(page, label) {
  await page.evaluate((l) => {
    const cards = [...document.querySelectorAll('.zh-action-card, .zh-action-row--btn')];
    cards.find((c) => (c.querySelector('strong, .zh-action-label')?.textContent ?? '') === l)?.click();
  }, label);
  await page.waitForTimeout(500);
}

// --- caso 1: leituras reais voltam com dado --------------------------------
{
  const page = await abrir({
    os_recycle_bin_list: { result: { success: true, data: [{ Name: 'a' }, { Name: 'b' }, { Name: 'c' }] } },
    os_service_list: { result: { success: true, data: [{ Name: 'mpssvc', Status: 'Running' }, { Name: 'outro', Status: 'Stopped' }] } },
    system_processes: { result: { success: true, data: { count: 231 } } },
  });

  checar('Liberar espaço começa sem afirmar nada', await sub(page, 'Liberar espaço'), 'Indisponível');
  await clicar(page, 'Liberar espaço');
  checar('Lixeira mostra a contagem real', await sub(page, 'Liberar espaço'), '3 itens na Lixeira');

  await clicar(page, 'Ver processos');
  checar('Processos mostra a contagem real', await sub(page, 'Ver processos'), '231 processos');

  await clicar(page, 'Firewall');
  checar('Firewall mostra o estado do SERVIÇO', await sub(page, 'Firewall'), 'Serviço em execução');

  await clicar(page, 'Diagnóstico ZARA');
  checar('Diagnóstico usa o self-status real', await sub(page, 'Diagnóstico ZARA'), '2/3 capacidades disponíveis agora.');

  // Cards sem backend continuam declarados como indisponíveis.
  for (const label of ['Limpar temporários', 'Gerenciar inicialização', 'Atualizar sistema']) {
    checar(`${label} segue declarado indisponível`, await sub(page, label), 'Indisponível');
  }
  await page.close();
}

// --- caso 2: executor falha -> o erro DELE aparece -------------------------
{
  const page = await abrir({
    os_recycle_bin_list: { result: { success: false, error: 'ERRO_DO_EXECUTOR: Lixeira não pôde ser lida.' } },
    os_service_list: { result: { success: false, error: 'ERRO_DO_EXECUTOR: PowerShell indisponível.' } },
  });
  await clicar(page, 'Liberar espaço');
  checar('falha da Lixeira mostra o erro do executor', await sub(page, 'Liberar espaço'), 'ERRO_DO_EXECUTOR: Lixeira não pôde ser lida.');
  await clicar(page, 'Firewall');
  checar('falha do Firewall mostra o erro do executor', await sub(page, 'Firewall'), 'ERRO_DO_EXECUTOR: PowerShell indisponível.');
  await page.close();
}

// --- caso 3: Lixeira vazia não vira "indisponível" -------------------------
{
  const page = await abrir({ os_recycle_bin_list: { result: { success: true, data: [] } } });
  await clicar(page, 'Liberar espaço');
  checar('Lixeira vazia é dita como vazia', await sub(page, 'Liberar espaço'), 'Lixeira vazia');
  await page.close();
}

console.log(falhas === 0 ? '\nPainel Sistema lê de verdade.' : `\n${falhas} verificação(ões) falharam.`);
await browser.close();
process.exit(falhas === 0 ? 0 : 1);
