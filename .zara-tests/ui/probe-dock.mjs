// Prova que os 6 botões do dock levam a um destino REAL.
import { createRequire } from 'node:module';
const { chromium } = createRequire(import.meta.url)('/opt/node22/lib/node_modules/playwright');
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1680, height: 980 } });
await p.addInitScript(() => {
  window.zaraIPC = {
    system:{metrics:async()=>({cpu:1,ram:2,disk:3}),info:async()=>({}),selfStatus:async()=>({capabilities:[]})},
    message:{send:async()=>({response:'ok'}),interrupt:async()=>({})},
    voice:{start:async()=>({}),stop:async()=>({}),status:async()=>({listening:false}),sendMicChunk:()=>{}},
    userMemory:{list:async()=>({success:true,facts:[]})},
    conversationHistory:{list:async()=>({messages:[],count:0})},
    action:{execute:async()=>({result:{success:true,data:{}}}), list:async()=>({os_volume:{name:'os_volume',description:'Ajusta o volume',category:'os',risk:'LOW'},files_read:{name:'files_read',description:'Le um arquivo',category:'files',risk:'LOW'}})},
    on:{stateChange:()=>()=>{},metrics:()=>()=>{},message:()=>()=>{},voiceLevel:()=>()=>{},voiceOutputAudio:()=>()=>{},reminderCreated:()=>()=>{},reminderFired:()=>()=>{}},
  };
});
await p.goto(process.argv[2], { waitUntil: 'load' });
await p.waitForTimeout(2000);
let falhas = 0;
function checar(n, real, esp) { const ok = real === esp; if (!ok) falhas++; console.log(`${ok?'OK ':'FALHOU'} ${n}: ${JSON.stringify(real)} (esperado ${JSON.stringify(esp)})`); }
async function titulo() { return p.evaluate(() => document.querySelector('.zh-section-view h1')?.textContent ?? (document.querySelector('.zh-content-top') ? '(Home)' : document.querySelector('.zh-system-row') ? '(Sistema)' : null)); }
async function voltarHome() { await p.click('.zh-nav-item:has-text("Hoje")'); await p.waitForTimeout(400); }

for (const [aria, esperado] of [
  ['Aplicativos', 'Aplicativos'],
  ['Arquivos e memórias', 'Memórias'],
  ['Ajuda — o que a ZARA sabe fazer', 'O que a ZARA sabe fazer'],
  ['Histórico de conversas', 'Conversas'],
]) {
  await voltarHome();
  await p.click(`.zh-dock-btn[aria-label="${aria}"]`);
  await p.waitForTimeout(700);
  checar(`botão "${aria}"`, await titulo(), esperado);
}

// Menu rápido: abre, tem só destinos reais, navega e fecha
await voltarHome();
await p.click('.zh-dock-btn[aria-label="Mais"]');
await p.waitForTimeout(350);
const itens = await p.$$eval('.zh-dock-menu-item', els => els.map(e => e.textContent));
checar('menu rápido lista destinos', JSON.stringify(itens), JSON.stringify(['Sistema','Projetos','Automações','ZARA Lab','Dispositivos','Configurações']));
await p.click('.zh-dock-menu-item:has-text("Automações")');
await p.waitForTimeout(700);
checar('menu navega de verdade', await titulo(), 'Automações');
checar('menu fecha depois de navegar', await p.$$eval('.zh-dock-menu', e => e.length), 0);

// Ajuda lê o registry real
await voltarHome();
await p.click('.zh-dock-btn[aria-label="Ajuda — o que a ZARA sabe fazer"]');
await p.waitForTimeout(800);
const corpo = (await p.textContent('.zh-section-view-body')) ?? '';
checar('Ajuda usa a descrição vinda do backend', corpo.includes('Ajusta o volume') && corpo.includes('Le um arquivo'), true);
checar('Ajuda mostra o nome real da action', corpo.includes('os_volume'), true);

// Nenhum botão do dock pode estar desabilitado
const desab = await p.$$eval('.zh-dock-btn[disabled]', e => e.length);
checar('nenhum botão do dock desabilitado', desab, 0);

// A lente fica CENTRADA na barra (o dock só existe na Home)
await voltarHome();
const eixo = await p.evaluate(() => {
  const d = document.querySelector('.zh-dock').getBoundingClientRect();
  const v = document.querySelector('.zh-dock-voice').getBoundingClientRect();
  return Math.round(Math.abs((d.x + d.width / 2) - (v.x + v.width / 2)));
});
checar('lente centrada na barra (desvio px)', eixo <= 2, true);

console.log(falhas === 0 ? '\nTodos os botões do dock levam a algum lugar real.' : `\n${falhas} verificação(ões) falharam.`);
await b.close();
process.exit(falhas === 0 ? 0 : 1);
