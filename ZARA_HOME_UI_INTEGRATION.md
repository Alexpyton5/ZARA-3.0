# Integração da Home Titanium Emerald — ZARA 3.0

## Exceção de governança registrada

`.claude/rules/governance.md` lista "UI Titanium Emerald" nas áreas
proibidas sem autorização, e `.claude/rules/time-zara.md` diz que a
Interface (papel 6) "só entra depois que a voz funcionar". Esta missão foi
autorizada explicitamente por Alex, por escrito, no chat, especificamente
para esta integração — não é uma mudança das regras em si
(governance.md/time-zara.md não foram tocados), é uma exceção pontual
registrada aqui. Voz, latência e microfone não foram tocados nesta sessão.

## O que existia antes

`frontend/src/renderer/App.tsx` renderizava um `<iframe>` apontando para
`./zara-titanium-emerald/index.html` — um build estático separado
(`frontend/public/zara-titanium-emerald/`), com seu próprio bundle,
desconectado de IPC. Exatamente o "mock visual separado" que Alex disse não
querer mais.

## O que foi feito

1. **Inspeção real do site** (`https://zara-titanium-emerald.p9jpk5w4m6.chatgpt.site/`):
   DOM/ARIA tree completa via accessibility tree, CSS computado
   (`getComputedStyle`), os dois arquivos CSS reais baixados
   (`index-CNIMZ_NU.css` 175KB + `home-hawkwEF1.css` 31KB), os bundles JS
   (`home-*.js`, `index-*.js`), e todos os assets referenciados no HTML.
   Nenhum screenshot foi usado como interface.
2. **Assets reais baixados e versionados** em
   `frontend/src/assets/zara-home/`: logo, imagem de fundo (core-glass),
   5 ícones de marca (SVG), e a fonte real (`roboto-regular.ttf` — o site
   chama de "Titanium Sans" via `@font-face`, mas é literalmente Roboto
   Regular renomeado; confirmado lendo a regra `@font-face` antes de
   decidir que era seguro redistribuir — Roboto é Apache-licensed).
3. **Paleta exata extraída do CSS computado**, não estimada visualmente:
   `--obsidian:#030706`, `--emerald:#20f4ae`, `--emerald-2:#00bd82`,
   `--text:#eef5f2`, `--glass:#08110ec2`, `--line:#dbefe729`, etc. — ver
   `frontend/src/renderer/styles/zara-home.css`.
4. **Componentes React reais** (não canvas, não imagem única):
   `Sidebar`, `Header`, `TextCommandInput`, `ForYouCard`,
   `CommunicationsCard`, `ActiveProjectCard`, `ToolsCard`, `SystemPanel`,
   `ZaraCore`, `VoiceDock` — em `frontend/src/renderer/components/zara-home/`.
5. **`App.tsx` renderiza `<ZaraHome/>` diretamente** — sem iframe, sem
   segundo Electron, sem segundo backend.

## Dados dinâmicos — o que está conectado de verdade

| Dado | Fonte | Status |
|---|---|---|
| Comando de texto | `window.zaraIPC.message.send` (canal já existente) | **CONECTADO** |
| Modo Voz (start/stop) | `window.zaraIPC.voice.start/stop` (canal já existente, mesmo do HUD/Orb) | **CONECTADO** |
| Estado do Core | `window.zaraIPC.on.stateChange` (canal já existente) mapeado para 11 estados pedidos pela missão | **CONECTADO** |
| CPU / RAM / Disco | `window.zaraIPC.system.metrics()` (canal já existente) | **CONECTADO** |
| Bateria / carregando | `navigator.getBattery()` (API real do Chromium) | **CONECTADO** |
| Nome do usuário | fixo (`"Alex Silva"`) | fallback — integração de conta fora do escopo desta missão |
| Foto do usuário | fallback com iniciais | sem robô; troca por foto real quando houver integração Google/Microsoft |
| Wi-Fi / rede | `os_wifi_status` já existe como action | NOT_CONNECTED_YET — canal existe, não foi ligado nesta sessão |
| Energia (planos) | `os_power_plan_list`/`os_power_plan_set` já existem | NOT_CONNECTED_YET — canal existe, não foi ligado nesta sessão |
| Segurança (firewall/antivírus) | nenhuma action correspondente | NOT_CONNECTED_YET — precisaria de action nova |
| Manutenção (limpeza) | nenhuma action correspondente exposta a esta tela | NOT_CONNECTED_YET |
| Para você / Comunicações (contagem) | nenhuma fonte real | NOT_CONNECTED_YET |
| Projeto ativo / progresso | nenhum conceito de "projeto" no backend hoje | NOT_CONNECTED_YET |
| Ferramentas (VS Code/Postman/Docker) | `os_app` action existe, mas esses 3 apps não estão no allowlist (`_SAFE_WINDOWS_APPS`) | botão chama a action real; o próprio backend recusa com mensagem clara — não finge sucesso |

## Fidelidade visual

Estrutura, cores, tipografia e layout geral seguem o site de referência
fielmente (dados extraídos, não estimados). O fundo (`core-glass.png`) foi
ajustado para opacidade reduzida após a primeira captura mostrar ele
dominando demais a composição — um ajuste, não uma perseguição de pixel.
Por instrução explícita da missão ("não perseguir perfeição agora"), não
foi feita uma comparação pixel a pixel região por região; isso fica para
uma missão dedicada de calibração visual.

## Prova real

- `npm run typecheck` — limpo.
- `npm run build` — sucesso, assets reais no bundle (`zara-logo-*.png`,
  `roboto-regular-*.ttf`, `core-glass-*.png`, CSS/JS com hash).
- `npm run dev` (Vite, porta 5173) aberto no Browser pane: sidebar
  funcional, Header com relógio real, campo de texto presente,
  **bateria real mudou de 60% para 62% entre duas capturas** (prova de
  dado dinâmico de verdade, não estático), botão de voz corretamente
  mostra "não conectado" fora do Electron, botão de enviar mensagem
  corretamente **desabilitado** quando `window.zaraIPC` não existe (não
  finge que enviou).
- Console do navegador sem erros.
- Testado fora do Electron real (só Vite dev server) — não há prova ainda
  de que dentro do Electron empacotado o preload expõe `window.zaraIPC`
  exatamente como esperado; isso é o próximo passo natural (rodar
  `npm run electron:dev` ou empacotar), não feito nesta sessão por não ter
  sido pedido um candidato físico.

## O que NÃO foi feito

- Nenhuma comparação pixel-a-pixel formal Site × Electron.
- Nenhum wiring de Wi-Fi/Energia (canais existem, não foram ligados).
- Nenhuma nova autenticação/foto de perfil real.
- Nenhum teste automatizado novo para os componentes React (fora de
  escopo do ZARA Continuous Validation, que é Python/pytest).
- Legado (`frontend/public/zara-titanium-emerald/`,
  `frontend/src/renderer/components/zara/`) não foi removido — continua
  no repo, sem uso a partir de `App.tsx` agora.
