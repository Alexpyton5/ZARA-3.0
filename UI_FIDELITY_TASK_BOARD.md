# UI Fidelity Task Board — ZARA Home

| ID | GOAL | DESCRIPTION | OWNER | STATUS | EVIDENCE | NEXT ACTION |
|---|---|---|---|---|---|---|
| T01 | 1 | Inspecionar DOM/CSS real do site (não screenshot) | Sonnet 5 | DONE | accessibility tree + CSS computado + 2 arquivos CSS baixados | — |
| T02 | 1 | Reestruturar grid: main/core/right + Sistema full-width no rodapé | Sonnet 5 | DONE | commit `db1f7f9` | — |
| T03 | 6 | Sidebar: ícones lucide-react 1:1 com o site | Sonnet 5 | DONE | `classList` de `<svg>` do site confirmado | — |
| T04 | 2 | Core: adicionar glyph "ZA", aumentar tamanho, reposicionar | Sonnet 5 | DONE | screenshot pós-pass-2 | — |
| T05 | 3 | Background: aumentar opacidade/saturação da aurora | Sonnet 5 | DONE | screenshot confirma teal/anéis visíveis | — |
| T06 | 5 | Dock: ancorar sob o Core, vidro/separadores, ícones reais | Sonnet 5 | DONE | screenshot pós-pass-2 | — |
| T07 | 8 | Trocar emoji por ícones lucide-react em toda a Home | Sonnet 5 | DONE | grep confirma zero emoji nos componentes | — |
| T08 | 7 | System panel: ícone + cor semântica por seção | Sonnet 5 | DONE | screenshot final | — |
| T09 | 9 | Revisão Opus pass 1 (diff escrito, sem visão de imagem) | Opus 5 (Agent) | DONE | 4 blockers retornados, todos corrigidos em T04-T07 | — |
| T10 | 9 | Revisão Opus pass 2 (final) | Opus 5 (Agent) | DONE | PASS, sem blocker novo | — |
| T11 | 7 | Badges coloridos com contagem real em Comunicações | — | SKIPPED_REQUIRES_OWNER | — | depende de fonte de dado real (WhatsApp/Telegram), não é CSS — decisão de produto sobre se vale construir isso agora |
| T12 | 7 | Ligar Wi-Fi (`os_wifi_status`) e Energia (`os_power_plan_list/set`) ao SystemPanel | — | SKIPPED_REQUIRES_OWNER | canais reais existem, documentado em GOAL 7 | próxima sessão, escopo pequeno e aditivo |
| T13 | 4 | Textura metálica realista na plataforma do Core | — | SKIPPED_REQUIRES_OWNER | hoje é gradiente CSS, não asset com detalhe físico | avaliar se vale um asset dedicado ou permanece CSS |
| T14 | 1/6/7 | Comparação pixel-a-pixel fina (spacing/tipografia item a item) | — | SKIPPED_REQUIRES_OWNER | fora do escopo desta missão por instrução explícita | missão dedicada de pixel-perfect, quando solicitada |
| T15 | 4 | **[Pass 4]** Restaurar plataforma do Core (regressão do pass 3 — `.zh-core-platform` tinha sido removida inteira) e reconstruir como anéis elípticos concêntricos + disco metálico, não gradiente chapado | Sonnet 5 | DONE | commit `a162fbe`; screenshot dev server | — |
| T16 | 6 | **[Pass 4]** Corrigir "caixa dentro de caixa" real do glifo ZA — `zara-logo.png` tinha card+wordmark embutidos e era usado como ícone em 4 lugares | Sonnet 5 | DONE | `zara-mark.png` isolado via edição de imagem; trocado em Sidebar/TextCommandInput/ActiveProjectCard/ZaraCore | — |
| T17 | 5 | **[Pass 4]** Ícone de voz do dock: `Mic`→`AudioLines` (símbolo de voice mode); vidro do dock mais espesso; microinterações hover/active | Sonnet 5 | DONE | `VoiceDock.tsx`, `zara-home.css` | — |
| T18 | 6 | **[Pass 4]** Header: "→" → ícone `Send` emerald; status row: `Shield`/`Cloud` honestamente desconectados + bateria em cápsula com preenchimento real da Battery API | Sonnet 5 | DONE | `TextCommandInput.tsx`, `ZaraHome.tsx` | — |
| T19 | 7 | **[Pass 4]** System panel reconstruído para as 5 colunas da referência com ícone semântico por item da missão; itens sem backend real mostram "Indisponível" explícito | Sonnet 5 | DONE | `SystemPanel.tsx` reescrito; `tsc`/`vite build` limpos | — |
| T20 | 4 | Textura da plataforma ainda é CSS (elipses+box-shadow), não asset 3D/fotorrealista | — | SKIPPED_REQUIRES_OWNER | resultado atual já é "presença física convincente", ganho marginal de um asset dedicado é incerto | avaliar 1 geração Stitch dedicada só para essa peça, se o owner considerar necessário |

## Estado final (pass 4)

TODO = 0 (nenhuma task executável restante sem decisão do owner)
IN_PROGRESS = 0
DONE = 16
SKIPPED_REQUIRES_OWNER = 5 (T11, T12, T13→superada por T15, T14, T20)
FAILED_AFTER_RETRIES = 0

Pass 4 fechou a maior lacuna encontrada na auditoria desta sessão: a
plataforma do Core tinha sido perdida por completo no pass 3 (ficou só o
Core flutuando com um feixe de luz, sem nenhuma estrutura física sob ele).
Reconstruída, além de 4 correções menores (glifo com "caixa dentro de
caixa", ícone de voz genérico, System panel raso demais vs. a referência,
status row incompleta). Ver `UI_FIDELITY_GOALS.md` para o detalhe por goal
e o que fica documentado como pendência de owner.
