# UI Fidelity Goals — ZARA Home (Titanium Emerald)

Referência absoluta: https://zara-titanium-emerald.p9jpk5w4m6.chatgpt.site/

## GOAL 1 — Canvas/Proportions
Status: DONE
Success Criteria: composição em colunas (main | core estreito | direita estreita) + faixa Sistema full-width no rodapé, batendo com a inspeção real do DOM do site.
Tasks: reestruturação de `ZaraHome.tsx`/`zara-home.css` (pass 1).
Evidence: screenshot 1280x800 comparado lado a lado com o site; commit `db1f7f9`.

## GOAL 2 — Core
Status: DONE
Success Criteria: glyph "ZA" visível, tamanho/posição próximos da referência, aparência de vidro fumê em vez de esfera verde chapada.
Tasks: `zaraLogo` renderizado dentro do Core; Core 128px→180px; reposicionamento para o topo da coluna.
Evidence: screenshot pós-pass-2; revisão Opus (PASS) sobre o diff escrito.

## GOAL 3 — Background
Status: DONE (fidelidade razoável, não pixel-exata)
Success Criteria: aurora/anéis visíveis, não um retângulo escuro plano.
Tasks: opacidade 0.22→0.55, `saturate(1.05) brightness(0.95)`, reposicionamento.
Evidence: screenshot confirma teal/anéis visíveis atrás da sidebar e do Core.

## GOAL 4 — Platform
Status: DONE (razoável)
Success Criteria: anel de titânio dando profundidade física ao Core.
Tasks: `.zh-core-platform` (300px, gradiente + box-shadow em camadas).
Evidence: visível no screenshot; não é fidelidade de "engineered structure" completa (sem textura metálica real), documentado como próximo passo.

## GOAL 5 — Dock
Status: DONE
Success Criteria: ancorado sob o Core (não sob a página inteira), aparência de vidro/separadores, ícones consistentes com o resto do sistema.
Tasks: movido para dentro da coluna do Core; separadores `.zh-dock-separator`; ícones lucide-react (Mic/MicOff, Grid3x3, Folder, HelpCircle, History, MoreHorizontal); botão de voz com gradiente radial + inset shadow.
Evidence: screenshot pós-pass-2; revisão Opus (PASS).

## GOAL 6 — Sidebar/Header
Status: PARTIAL
Success Criteria: ícones por item de navegação (feito), status row Wi-Fi/bateria/hora no canto superior direito (feito), mas sem comparação fina de spacing/typography item a item.
Tasks: ícones lucide-react confirmados 1:1 com o `<svg class="lucide-*">` real do site; status row com ícones reais (não emoji).
Evidence: screenshot; inspeção de `classList` dos ícones do site de referência.

## GOAL 7 — Cards/System
Status: PARTIAL
Success Criteria: cards não devem parecer "nested boxes" excessivas; System panel com cor semântica.
Tasks: System panel ganhou ícone por seção + cor semântica (branco=neutro, esmeralda=ativo, cinza=indisponível) nesta sessão. Para Você/Comunicações/Projeto Ativo continuam com placeholders textuais simples (`NOT_CONNECTED_YET`) em vez dos badges coloridos com contagem do site — decisão deliberada (não inventar dado fake), não um gap de fidelidade visual não resolvido.
Evidence: screenshot final.

## GOAL 8 — Typography/Icons
Status: DONE (typography) / DONE (icons)
Success Criteria: mesma fonte (Roboto renomeada "Titanium Sans", confirmada via @font-face real do site) e mesma biblioteca de ícones (lucide-react, confirmada via inspeção de classe).
Tasks: fonte baixada e aplicada; ícones trocados de emoji para lucide-react em Sidebar/VoiceDock/status row/SystemPanel.
Evidence: `roboto-regular.ttf` no bundle; nenhum emoji restante nos componentes principais.

## GOAL 9 — Final Fidelity
Status: DONE (para o escopo desta missão)
Success Criteria: revisão final Opus não encontra blocker grande.
Tasks: 2 rodadas de revisão Opus (pass 1: 4 blockers identificados e corrigidos; pass 2: PASS, sem blocker novo).
Evidence: ver `UI_FIDELITY_TASK_BOARD.md` e as duas respostas do agente Opus nesta sessão.

## O que fica para uma missão de polimento futura (não blockers de "está pronta para uso")

- Comparação pixel-a-pixel fina de spacing/tipografia item a item (explicitamente fora do escopo desta missão — "não perseguir perfeição agora").
- Badges coloridos com contagem real em Comunicações (depende de fonte de dado real, não de CSS).
- Textura metálica mais realista na plataforma do Core (hoje é gradiente/box-shadow, não um asset com detalhe físico).
- Wi-Fi/Energia: canais reais existem (`os_wifi_status`, `os_power_plan_list/set`) mas não foram ligados nesta sessão.
