# UI Fidelity — Handoff

## Current goal
GOAL 9 (Final Fidelity) — pass 3 concluído. Sessão encerrando por limite de uso;
este documento permite continuar sem perder contexto.

## Completed this session (3 passes, all committed)
- Pass 1 (`db1f7f9`): composição real (main | core estreito | direita estreita
  + Sistema full-width no rodapé), ícones lucide-react reais na sidebar, Core
  com plataforma de anéis (aproximação).
- Pass 2 (`ebe3fa6`): glyph ZA dentro do Core, aurora com opacidade maior,
  dock ancorado sob o Core com vidro/separadores, System panel com ícone +
  cor semântica.
- Pass 3 (`509769e`): **correção crítica de asset** — `core-glass.png` não é
  fundo, é a esfera de vidro em si (`<img class="te-sphere-art">` no bundle
  real do site). O fundo real é `/titanium/aurora-master-refined.png`
  (montanhas + aurora + reflexo, baixado e em uso agora). Core reconstruído
  com glow CSS + imagem de vidro real + glyph + feixe de luz vertical
  (`.zh-core-shaft`, 143px, gradiente igual ao `.te-platform-shaft` real).

## Next exact task
Nenhuma task bloqueante pendente. Se continuar:
1. Confirmar visualmente (screenshot) que o Browser pane voltou a funcionar
   normalmente — no fim desta sessão ele parou de compor frames
   (`Screenshot timed out ... pane is not displayed`), possivelmente por
   reinício de sessão/cota. Não é um bug do código: `npm run build` e
   `npm run typecheck` continuam limpos depois da pass 3.
2. Revisar `.zh-core-mark` (130×96px) e `.zh-core-shaft` (143px) contra o
   screenshot real assim que o Browser pane voltar — esses dois valores
   foram calibrados por medida exata do CSS do site (`.te-core-mark{width:
   141px;height:104px}`, `.te-platform-shaft{height:143px}`), não por olho,
   mas nunca foram vistos renderizados juntos depois do ajuste.
3. Ver `UI_FIDELITY_GOALS.md`/`UI_FIDELITY_TASK_BOARD.md` para os 4 itens
   SKIPPED_REQUIRES_OWNER (Wi-Fi/Energia binding, badges de comunicação,
   textura metálica da plataforma, pixel-perfect fino).

## Files being edited (all committed, working tree limpa)
- `frontend/src/renderer/components/zara-home/ZaraCore.tsx`
- `frontend/src/renderer/components/zara-home/ZaraHome.tsx`
- `frontend/src/renderer/styles/zara-home.css`
- `frontend/src/assets/zara-home/aurora-master-refined.png` (novo)

## Latest Site/Electron comparison
Última comparação visual válida (antes do Browser pane parar de compor
frames): Electron mostrando esfera de vidro real com glyph ZA, fundo de
aurora/montanha real com reflexo n'água, feixe de luz vertical ligando o
Core ao dock, dock com separadores/ícones lucide-react, System panel com
ícone+cor semântica por seção. Avaliação: "recognizably very close" à
referência (confirmado por 3 revisões Opus, todas PASS).

## Remaining blockers
Nenhum blocker grande de fidelidade identificado pelas 3 revisões Opus.
Itens de polimento (não blockers): textura metálica da plataforma, badges
coloridos com contagem real em Comunicações, Wi-Fi/Energia não ligados
(canais reais existem: `os_wifi_status`, `os_power_plan_list/set`).

## DEV AI Router — usado, achado externo ao repo
`C:\Users\alexp\Documents\SISTEMA DE PROVEDORES FREE\devairouter\` —
NÃO copiado para dentro da ZARA, NÃO alterado. `status`: qwen_local OK,
nemotron OK (nvidia/nemotron-3-super-120b-a12b), opencode_zen UNREACHABLE,
deepseek/kimi NOT_CONFIGURED, paid calls BLOCKED. Usado uma vez via
`python -m devairouter.cli ask ... --only nemotron` para comparar tokens
de cor CSS (texto puro, sem imagem — o router não faz visão). Achado:
`--zh-muted` (#9fb3ac, usado como cor de TEXTO secundário) tem valor
diferente do `--muted` do site (#262626) — falso positivo: o `--muted` do
site é um tom de FUNDO (convenção shadcn), o equivalente real seria
`--muted-foreground`, não capturado na extração original. Não foi corrigido
porque `#262626` como cor de texto sobre fundo escuro ficaria ilegível —
Nemotron analisa, mas a decisão de aplicar ou não é do Sonnet, como
instruído.

## Google Stitch — testado, não usado no rebuild
Autenticado na aba do navegador interno. Teste de 5 min: criou um projeto
descartável, gerou uma tela simples, exportou um `.zip` real com
`code.html` + `DESIGN.md` + `screen.png`. Capacidade confirmada. Não usado
para reconstruir a Home real porque a extração direta de DOM/CSS/assets do
site (já em uso) produz valores exatos da referência, e uma reconstrução
generativa via prompt seria uma reinterpretação, não uma cópia — contrário
à instrução de "não redesenhar". Artefatos de teste apagados.
