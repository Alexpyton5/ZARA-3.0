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
Status: DONE (rebuilt — pass 3 tinha removido a plataforma por engano)
Success Criteria: anel de titânio dando profundidade física ao Core.
Tasks: pass 3 (`509769e`) removeu `.zh-core-platform` inteira ao corrigir o
bug do `core-glass.png` usado como background — ficou só o feixe de luz,
sem plataforma nenhuma. Pass 4 reconstruiu com `.zh-platform-seat` (disco
metálico sob a esfera) + 4 `.zh-platform-ring` elípticos concêntricos
(perspectiva, opacidade/luminância decrescente para fora, brilho metálico
no topo, viés de brilho esmeralda só na borda inferior — material é
titânio/metal fumê, verde é só acento de energia).
Evidence: screenshot 1280x800 (dev server) — anéis visíveis com boa
profundidade; `tsc --noEmit` e `vite build` limpos.

## GOAL 5 — Dock
Status: DONE
Success Criteria: ancorado sob o Core (não sob a página inteira), aparência de vidro/separadores, ícones consistentes com o resto do sistema.
Tasks: movido para dentro da coluna do Core; separadores `.zh-dock-separator`; ícones lucide-react (Grid3x3, Folder, HelpCircle, History, MoreHorizontal); botão de voz com gradiente radial + inset shadow. Pass 4: ícone central trocado de `Mic`/`MicOff` (microfone genérico) para `AudioLines` (símbolo de "voice mode"); vidro do dock mais espesso (gradiente de 2 camadas + sombra em 4 camadas); microinterações Apple-like (hover = leve elevação, active = scale 0.97) nos botões do dock e no botão de envio do header.
Evidence: screenshot pós-pass-2; revisão Opus (PASS); screenshot pass 4 (dev server).

## GOAL 6 — Sidebar/Header
Status: DONE (era PARTIAL)
Success Criteria: ícones por item de navegação (feito), status row Wi-Fi/bateria/hora no canto superior direito (feito), mas sem comparação fina de spacing/typography item a item.
Tasks: ícones lucide-react confirmados 1:1 com o `<svg class="lucide-*">` real do site; status row com ícones reais (não emoji). Pass 4: identificado e corrigido um artefato de "caixa dentro de caixa" real — `zara-logo.png` incluía um card escuro + wordmark "ZARA" embutidos na imagem, e essa mesma imagem estava sendo usada como ÍCONE (28px na sidebar, 22px no header, dentro do Core) nos três lugares. Isolado o glifo "ZA" puro sem fundo (`zara-mark.png`, via edição de imagem) e trocado nos 4 usos (Sidebar, TextCommandInput, ActiveProjectCard, ZaraCore). Header: botão de enviar trocado de caractere "→" para ícone `Send` (lucide) emerald. Status row: adicionados `Shield`/`Cloud` ao lado do `Wifi` (todos honestamente marcados como não conectados); bateria trocada de ícone lucide para cápsula estilo iPhone com preenchimento real da Battery API.
Evidence: screenshot pass 4 (dev server) confirma glifo limpo sem card nos 4 locais; `tsc --noEmit` limpo.

## GOAL 7 — Cards/System
Status: DONE (era PARTIAL)
Success Criteria: cards não devem parecer "nested boxes" excessivas; System panel com cor semântica.
Tasks: System panel ganhou ícone por seção + cor semântica (branco=neutro, esmeralda=ativo, cinza=indisponível) nesta sessão. Para Você/Comunicações/Projeto Ativo continuam com placeholders textuais simples (`NOT_CONNECTED_YET`) em vez dos badges coloridos com contagem do site — decisão deliberada (não inventar dado fake), não um gap de fidelidade visual não resolvido. Pass 4: System panel reconstruído para a estrutura de 5 colunas da referência (Estado do dispositivo / Manutenção / Segurança / Energia / Diagnóstico inteligente), com o ícone semântico específico de cada item pedido na missão (storage, trash, power+arrow, monitor, refresh, scan/pulse, magnifier, shield+check, shield, key, bug, gauge, leaf). Cada item sem ação real conectada mostra "Indisponível" explícito em vez de um botão morto ou dado fabricado. Card de diagnóstico ganhou uma onda ambiente puramente decorativa (não é telemetria real).
Evidence: screenshot pass 4 (dev server, viewport largo) mostra as 5 colunas legíveis e sem sobreposição; `tsc --noEmit` e `vite build` limpos.

## GOAL 8 — Typography/Icons
Status: DONE (typography) / DONE (icons)
Success Criteria: mesma fonte (Roboto renomeada "Titanium Sans", confirmada via @font-face real do site) e mesma biblioteca de ícones (lucide-react, confirmada via inspeção de classe).
Tasks: fonte baixada e aplicada; ícones trocados de emoji para lucide-react em Sidebar/VoiceDock/status row/SystemPanel.
Evidence: `roboto-regular.ttf` no bundle; nenhum emoji restante nos componentes principais.

## GOAL 9 — Final Fidelity
Status: DONE (para o escopo desta missão) + Pass 4 concluído
Success Criteria: revisão final Opus não encontra blocker grande.
Tasks: 2 rodadas de revisão Opus (pass 1: 4 blockers identificados e corrigidos; pass 2: PASS, sem blocker novo). Pass 4 (esta sessão): maior lacuna identificada era a PLATAFORMA do Core (regressão do pass 3, ver GOAL 4) — corrigida, junto com os itens de GOAL 5/6/7 acima.
Evidence: ver `UI_FIDELITY_TASK_BOARD.md` e as duas respostas do agente Opus nesta sessão; checkpoint git `a162fbe`.

## O que fica para uma missão de polimento futura (não blockers de "está pronta para uso")

- Comparação pixel-a-pixel fina de spacing/tipografia item a item (explicitamente fora do escopo desta missão — "não perseguir perfeição agora").
- Badges coloridos com contagem real em Comunicações (depende de fonte de dado real, não de CSS).
- Plataforma do Core: os anéis (pass 4) ainda são CSS (elipses + box-shadow), não um asset 3D-rendered com textura de titânio fotorrealista — se a diferença visual residual for considerada relevante, avaliar 1 geração Stitch dedicada só para essa peça.
- Wi-Fi/Energia: canais reais existem (`os_wifi_status`, `os_power_plan_list/set`) mas não foram ligados nesta sessão — decisão de owner pendente (T12).
- `zara-mark.png` gerado por edição de imagem ficou com ~1.4MB (canvas grande com muita área transparente); funciona, mas poderia ser recortado/otimizado numa passada de performance.
