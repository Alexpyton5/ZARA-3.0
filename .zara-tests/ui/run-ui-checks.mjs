// Roda todos os probes de UI contra um build local, em sequência.
//
// Por que existe: a Home só pode ser conferida renderizando. Sem isto, cada
// sessão redescobre na unha que precisa buildar, servir e injetar um
// `window.zaraIPC` no formato certo — e no caminho alguém acaba "conferindo"
// a tela lendo o código, que é justamente o que a regra de evidência proíbe.
//
// Fluxo: `vite build` -> servidor estático em 127.0.0.1 -> cada probe.
// Nada aqui fala com o sidecar: os probes injetam o formato real dos
// handlers. Isso prova o RENDERER, não o runtime empacotado — o nível de
// evidência continua sendo RUNTIME_AUTOMATED, nunca PACKAGED_RUNTIME.
//
// uso: node .zara-tests/ui/run-ui-checks.mjs [porta]
import { spawn, spawnSync } from 'node:child_process';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const raiz = normalize(join(fileURLToPath(new URL('.', import.meta.url)), '..', '..'));
const frontend = join(raiz, 'frontend');
const dist = join(frontend, 'dist-frontend');
const porta = Number(process.argv[2] || 8231);

const PROBES = [
  ['composição da Home', 'probe.mjs', [`${join(raiz, '.zara-tests/ui/headless-current.png')}`, 'idle']],
  ['seções da Sidebar', 'probe-sections.mjs', ['/tmp/zara-ui']],
  ['comando de texto', 'probe-texto.mjs', ['/tmp/zara-ui']],
  ['estados do Core', 'probe-estados.mjs', []],
  ['nada inventado', 'probe-sem-mentira.mjs', ['/tmp/zara-ui']],
  ['Ferramentas', 'probe-ferramentas.mjs', []],
  ['botão de voz', 'probe-voz.mjs', []],
];

const TIPOS = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css',
  '.png': 'image/png', '.svg': 'image/svg+xml', '.ttf': 'font/ttf', '.json': 'application/json',
};

console.log('> vite build');
const build = spawnSync('npx', ['vite', 'build'], { cwd: frontend, encoding: 'utf8' });
if (build.status !== 0) {
  console.error(build.stdout || '', build.stderr || '');
  process.exit(1);
}
if (!existsSync(join(dist, 'index.html'))) {
  console.error(`build não produziu ${dist}/index.html`);
  process.exit(1);
}

const servidor = createServer(async (req, res) => {
  // Só serve o que está dentro de dist-frontend.
  const pedido = decodeURIComponent((req.url || '/').split('?')[0]);
  const alvo = normalize(join(dist, pedido === '/' ? 'index.html' : pedido));
  if (!alvo.startsWith(dist)) { res.writeHead(403).end(); return; }
  try {
    const corpo = await readFile(alvo);
    res.writeHead(200, { 'content-type': TIPOS[extname(alvo)] || 'application/octet-stream' });
    res.end(corpo);
  } catch {
    res.writeHead(404).end();
  }
});

await new Promise((resolve) => servidor.listen(porta, '127.0.0.1', resolve));
const url = `http://127.0.0.1:${porta}/`;
console.log(`> servindo ${dist} em ${url}\n`);

let reprovados = 0;
for (const [nome, arquivo, extras] of PROBES) {
  const codigo = await new Promise((resolve) => {
    const p = spawn('node', [join(raiz, '.zara-tests/ui', arquivo), url, ...extras], { stdio: ['ignore', 'pipe', 'pipe'] });
    let saida = '';
    p.stdout.on('data', (d) => { saida += d; });
    p.stderr.on('data', (d) => { saida += d; });
    p.on('close', (c) => {
      const ok = c === 0;
      if (!ok) reprovados += 1;
      console.log(`${ok ? 'PASSOU' : 'FALHOU'}  ${nome}`);
      if (!ok) console.log(saida.split('\n').map((l) => `        ${l}`).join('\n'));
      resolve(c);
    });
  });
  void codigo;
}

servidor.close();
console.log(reprovados === 0
  ? `\n${PROBES.length}/${PROBES.length} verificações de UI passaram.`
  : `\n${reprovados} de ${PROBES.length} verificações de UI falharam.`);
process.exit(reprovados === 0 ? 0 : 1);
