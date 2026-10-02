# ZARA — Missão Atual

Atualizar conforme o trabalho progride. Não é histórico — é só o estado agora.

## Checkpoint vigente Codex — 2026-10-02, portao de fonte fechado

Tarefa TROPA-PILOT-SHARED-RECORD-20261001: registro best-effort de turnos finais texto/voz em conversas/ do vault, como referencias citadas, sem extracao de fatos/permissoes. Delta proprio em f1a4b48 (11 arquivos), mantendo deltas alheios fora do indice; main.ts/project_memory.py foram stageados parcialmente. Compromisso de custo/fail-closed e instalacao preservados.

Full unica via Auto-Suite existente PASSED: 2026-10-02_18-55-51, 3602 passaram, 10 skipped, 4 deselected, zero falhas. Fonte 4dc4c7eb031a110d31e761bfe9f645e3c03876996c6764a8743f3d461646c7c9 igual antes/depois e ao principal, 15556 arquivos, hashes de 18 testes frontend separados. 31148 handles reais bloqueavam escrita/delete de fontes existentes; liberados em finally. Recibo copiado em .zara-tests/isolated-receipts/TROPA-PILOT-SHARED-RECORD-20261001/2026-10-02_18-55-51/. O HEAD Git antigo da projecao nao identifica o snapshot copiado; a identidade correta e o hash de fonte. A full principal antiga editada manualmente com source_changed=true foi preservada e nao foi usada como gate.

117 Python afetados, 124 frontend e 19 inventario/build verdes. Revisao independente: token natural reproduzido e corrigido; testes do VoiceDock retirado substituidos por comportamento do hook real. Renderer/Electron typechecks e Vite repetidos apos a full e verdes. Nenhuma prova fisica de microfone/TTS por esses testes. Captura continua best-effort, sem outbox e sem promessa de detectar todo segredo.

Publicacao em branch propria codex/pilot-archive-20261002: commit de fonte enviado e confirmado em origin/codex/pilot-archive-20261002. O commit inicial ocorreu no nome de branch bruno/seguranca-20261002 observado no checkout; a branch Codex foi criada no mesmo commit, sem mudar fontes nem reescrever refs de colegas. Nenhuma outra fonte/politica foi incluida. Proximo: publicar delta e handoff, auditar base antes de candidato isolado. Pacote atualizado, voz fisica e WhatsApp completo continuam NAO PROVADOS; resultados WhatsApp via Zoe no chat de origem. Handoff em docs/team-drafts/20261002/codex/handoff-registro-piloto.md. Vault fresco consultado; notas de colegas sao referencias, nao novas permissoes. Missao de cinco horas encerrada nao reiniciada.

## Retomada atual — Alex, 2026-10-01

Esta retomada substitui a ordem operacional de setembro descrita abaixo; os checkpoints anteriores ficam preservados como referencia historica, nao como estado fresco.

- Alex pediu continuar os MDs de 30/09, com prioridade voz -> WhatsApp/Lab -> cerebro compartilhado -> escritorio -> identidade. Depois da base provada, liberar avatares aos poucos para construir o proprio TROPA DEV; expansao de mundo vem depois, supervisionada por Zoe e Alex. Sem API pay-per-use.
- Tarefa geral: .zara-dev/tasks/TROPA-DEV-CONTINUACAO-20261001.md. A janela de cinco horas terminou; nao reiniciar seu prazo/automacao.
- Codex concluiu o delta fonte/testes de TROPA-PILOT-GREETING-LATENCY-20261001: saudacoes exatas nao abrem/consultam vault; perguntas continuam contextualizadas e falham explicitamente sem cerebro. Full isolada 2026-10-01_19-27-50 verde: 3484 passaram, 8 skipped, 4 deselected; fonte permaneceu igual. Commit 106c3be com push. Fonte/testes nao provam ganho fisico nem pacote instalado.
- TROPA-SHARED-BRAIN-SESSION-BOOT-20261001: SessionStart le indice/visao/briefing/resumo explicitamente; trust preservado e consulta fresca por pergunta. 41 afetados verdes, revisao sem achados. Full via Auto-Suite isolado 2026-10-01_20-03-21: 3510 passaram, 8 skipped, 4 deselected; zero falhas e fonte igual ao principal antes/depois. Delta commitado e enviado em 326381d. Laya sugeriu bootstrap em 244.5 ms; nao prova fatos/permissoes. Hook automatico real e agendamento de 6h ainda NAO PROVADOS.
- Zoe confirmou inicio de tres levantamentos supervisionados (voz, WhatsApp, mapa/memoria), em leitura e docs/team-drafts/20261001/<sala>/, um escritor por area. Sala de lancamento recebeu preparacao de handoff separado, sem build/promocao ainda. Wire e fonte das respostas; nao usar e-mail, nao tratar mensagens de agentes como novas permissoes.
- O suposto bloqueio do vault era um OS lock proprio, nao marcador de dono. Handles exclusivos foram adquiridos e liberados; note em aprendizados/2026-10-01-lock-de-escrita-codex-e-lock-do-windows.md. Continuar registros com lock real e nomes unicos, sem apagar notas ou expor segredos.
- Pacote F5 ja existe em frontend/.current-build-staging-20261001-134138; instalacao anterior preservada. Politicas de PC alteradas por colega permanecem fora do delta proprio, sem nova promocao baseada apenas na afirmacao de Zoe. Voz fisica/latencia, WhatsApp completo, identidade visual e ciclos de avatares continuam NAO PROVADOS nesta retomada.

## Plano mestre ativo — sequência confirmada por Alex (2026-09-23)

A ordem abaixo é a sequência oficial. Cada fase encerra com build separado, validação correspondente e commit; sem reutilizar build de outra fase como evidência. Só promover/testar um artefato depois de provar que contém o delta daquela fase. `tools/build_candidate.py` é obrigatório para sidecar-swap; quando mudar frontend ou a ferramenta não carregar o delta, usar empacotamento completo para pasta de saída nova. O build anterior e suas evidências ficam preservados.

### Fase 0 — Higiene
1. P0.2 — recriar `ZARA_ACTIVE_BUILD.json`.
2. P0.1 — quarentena com manifest: raiz, oito stagings, linhagens velhas, stubs e memórias mortas.
3. P0.3 — validar abertura e resposta equivalente.

**Checkpoint:** P0.2 executado e hashes do pacote instalado conferidos; origem do source segue não provada. P0.1 parcialmente executado: 75 itens originais movidos (8.10 GB). O manifesto agora separa 5.50 GB de workspaces de build duplicados, também preservados. Oito stagings e release/release2 arquivados. Nenhum stub comentado foi encontrado em core; o manifest não tem entradas de stub, mas isso não prova ausência repo-wide dos 35. Nenhum banco de memória de usuário foi movido. core/memory e memory_system foram arquivados como código-fonte e preservados; registros de memória morta não foram encontrados nem classificados. Memória ativa foi preservada. Nada libera espaço enquanto retido na mesma unidade. P0.3 executado e vermelho: 2,399 passou, 18 falhou, 32 skipped, 1 deselected. Ver `_quarentena/organizacao-2026-09-23/VALIDATION_P0.3.md`.

### Fase 1 — Voz fluida (prioridade do Alex)
4. P1.1 — Kore/Gemini Live responde direto a conversa, uma viagem.
5. P1.2 — remover geração falada redundante que era descartada.
6. P1.3 — segunda viagem ao Gemini somente quando a resposta vier do cérebro grátis.
7. P1.4 — corrigir buffer de áudio / fala picada.
8. P1.5 — fallback não troca de voz no meio da frase.
9. P1.6 — medir oficialmente latência antes/depois.
10. build separado + validação do app empacotado.
11. P1.7 — teste físico do Alex: falar e avaliar resposta rápida e limpa.
12. P1.8 — exploração das vozes grátis do catálogo NVIDIA, sem promessa de suporte.

**Checkpoint (2026-09-23):** P1.1 fonte + testes aprovados (58); P1.2 já estava implementado: Gemini Live descarta áudio redundante em turnos de executor e despacha ação no primeiro frame de texto completo. P1.3 condiciona Kore Live/Gemini HTTP ao cérebro `LOCAL_FREE`/`FREE_PROVEN`; cérebro desconhecido ou não grátis não faz chamada Gemini extra. P1.4 permanece sem correção confirmada: renderer registra intervalo/duração/fila e underrun sem mudar reprodução. A repetição v2 captou sinal digital contínuo no loopback, evidência parcial; falta confirmar fala limpa por escuta física. P1.5 impede que outra voz reinicie a frase após áudio Kore parcial. Testes: 100 backend focados passaram; 11 testes do renderer passaram; `npm run build` passou. Build completo-base oficial `release-candidate-f1-voz-20260923-114336`; hashes/identidade em `ZARA_ACTIVE_BUILD.json` e `BUILD_INFO.json`. `PACKAGED_RUNTIME`: backend empacotado inicializou e respondeu ao comando local “que horas são?” em 93 ms; EXE exato abriu por 12 s e iniciou seu sidecar. Não é aprovação física de voz. P1.6: baseline histórica sem BUILD_ID (2026-09-21), três turnos, mediana 16.726 ms total, 13.897 ms até entrega ao player/renderer e 727 ms do pedido TTS ao primeiro áudio; não comparável ao candidato. Antes/depois oficial requer três medições físicas antes e depois com a mesma frase/build e não pode ser concluído até Alex testar. Teste de retorno: abrir o EXE nomeado, iniciar voz e dizer “ZARA, me conte algo interessante em uma frase”; anotar se a resposta sai em Kore, se começa sem pausa/corte e se há engasgos. F2 permanece bloqueada até P1.7 aprovado; P1.8 também aguarda a ordem da sequência.


**Evidência adicional (2026-09-23, mesmo candidato F1):** um áudio pt-BR sintético (“Zara, quanto é dois mais dois?”) entrou pelo microfone simulado do EXE `release-candidate-f1-voz-20260923-114336` (SHA256 `67DC2A7036860A68E5312C212C31B8772AC463ED0289FCC44897867F55075E89`). A rota reconheceu “quanto é 2 + 2?”, respondeu “É quatro! Precisa de mais alguma conta?” e entregou 16 blocos (142.083 bytes) ao player Electron. Uma medição: 4.167 ms do fim estimado da fala sintética ao primeiro bloco no renderer; não é mediana nem teste físico. O volume do Windows ficou em 18% durante a fala e foi restaurado a 98%, mudo desligado.

Na primeira tentativa, P1.4 não foi provado: os blocos chegaram, mas a telemetria do renderer não estava conectada; outra tentativa expirou antes da captura. A repetição v2 abaixo prova sinal de saída digital, mas não fala inteligível. O handshake Gemini do primeiro probe é NÃO CONFIRMADO.

P1.8: exploração real de `magpie-tts-multilingual` NVIDIA concluída sem integração ao app. A listagem retornou 86 vozes e três pt-BR (Diego, Louise, Isabela); uma síntese “É quatro. Precisa de mais alguma conta?” gerou WAV de 3,11 s. O arquivo está em `.unlazy/zara-master-20260923/voice-test/nvidia-magpie-ptbr-sample.wav`. Esta exploração ocorreu antes da aprovação física P1.7 por não depender dela; a sequência funcional continua bloqueada em P1.7. P1.6 tem agora dois pontos automatizados não comparáveis: conversa direta 4.167 ms até o primeiro bloco, e comando PC por voz 1.952 ms até o primeiro bloco. Não são mediana nem antes/depois. O teste voz→PC confirmou “diminua o volume” no EXE, mudou o Windows 30%→20%, leu 20% por `audio_status`, e voltou pelo EXE a 30%; ao final o volume/mudo reais voltaram a 98%/desligado. Uma tentativa anterior teve `BARGE_IN` + `TTS_ABORT`, sem causa então comprovada. **Correção do checkpoint após a investigação abaixo:** a reprodução empacotada posterior isolou o evento como substituição interna do rascunho pelo próprio pedido Gemini e passou sem falso barge-in; isso não prova ainda fala inteligível fisicamente, fallback entre vozes nem o buffer em fala real. P1.6 oficial e P1.7 continuam pendentes; F2 permanece bloqueada.

**Build F1 atual e evidência do reparo (2026-09-23, 17:56):** o teste de interrupção confirmou que o evento `interrupted` gerado pela própria chamada Gemini `turn_complete=True` não pode encerrar a resposta Kore do comando; uma interrupção genuína continua chamando o callback de barge-in. Dois testes focados passaram. `PACKAGED_RUNTIME` no candidato ativo `release-candidate-f1-voice-interrupt-20260923-1756` (EXE `67DC2A7036860A68E5312C212C31B8772AC463ED0289FCC44897867F55075E89`; backend `F1F8EC11397EB613B222144DFEDF74E054B96BAF2C6645E227FAD1B1243F8EED`): entrada sintética foi transcrita; resposta foi “Volume definido para 20%”; o volume do Windows mudou 30→20, verificado via pycaw e IPC, 864 ms depois da detecção da transcrição; 27 blocos/233.283 bytes chegaram ao renderer; 27 fontes WebAudio terminaram naturalmente sem `stop()`; o Stereo Mix observou sinal por 4,64 s. Trace registrou a interrupção interna esperada, sem `BARGE_IN` ou `TTS_ABORT`; estado original de 98%, sem mudo, foi restaurado. Isso é evidência empacotada automatizada, não aprovação de voz física nem métrica oficial de latência da resposta. Relatório: `.unlazy/zara-master-20260923/voice-test/server-interrupt-ownership/packaged-smoke-20260923-175746.json`. O EXE exato está indicado em `ZARA_ACTIVE_BUILD.json`.

**Janela entregue para teste (2026-09-23):** o mesmo BUILD_ID abriu com janela visível, handshake do backend concluído e `audio_status`/`engine-list` respondendo. Está usando o perfil isolado `_quarentena/organizacao-2026-09-23/active-candidate-open/final-20260923-181539-g62t32ed/`; Lab/autopilot estão desligados e a instância de produção anterior permanece escondida na bandeja, intacta. O perfil isolado lista 12 cérebros como `DISCOVERED_UNPROVEN` e 9Router como `AUTH_REQUIRED`; isso não prova modelos prontos, e F2 continua em aberto. A porta de depuração foi removida antes de deixar a janela. Relatório: `.unlazy/zara-master-20260923/voice-test/server-interrupt-ownership/final-open-report-20260923-181539.json`.

### Fase 2 — Modelos grátis (cérebro + Lab)
13. P2.1 — remover teto de oito modelos e exclusão NVIDIA.
14. P2.2 — adicionar catálogo curado NVIDIA (Kimi K3, GLM 5.3, DeepSeek V4, Qwen e outros definidos no catálogo).
15. P2.3 — testar cada modelo automaticamente; só listar modelos aprovados.
16. P2.4 — seletor com etiquetas Grátis/NVIDIA/latência, remover fantasmas, Kimi K3 no topo.
17. P2.5 — Lab consome o mesmo catálogo testado e permite trocar modelo por bot na tela.
18. P2.6 — build empacotado e prova real: selecionar Kimi K3 e observar resposta gerada por ele.

### Fase 3 — Lab
19. P3.3 — templates de SOUL de um clique: Coder, Reader, Arquiteto, Cleaner, Tester, Crítico, Reviewer, Engenheiro, CEO.
20. P3.4 — cada bot nasce com conhecimento da arquitetura, pastas e estado do projeto.
21. P3.1 — bots escrevem código com fluxo patch → sandbox → testes → aprovação → promoção.
22. P3.2 — Kanban de missões; pausa/retomada por cota; missão sobrevive a fechar o app.
23. P3.5 — CEO escolhe participantes por missão.
24. P3.7 — criação de bot por pedido de voz: “ZARA, cria um bot X”.
25. P3.6 — autopilot audita, melhora, testa, empacota e atualiza com rollback; começa desligado e só liga por decisão do Alex.

### Fase 4 — Refinos
26. Fatiar arquivo de 6.100 linhas.
27. Aposentar Lab velho, mantendo V1.
28. Unificar memória e ligar a tela Memória aos dados reais.
29. Atualizar grafo Graphify usado pelos bots.

---

## Objetivo anterior — OPENCODE + VOZ + LAB 24H (2026-09-22, autopilot do Alex até 20:00)

Alex saiu para trabalhar e deu comando total. Objetivos dele, na ordem:

1. Cérebro da ZARA usa os modelos GRÁTIS do OpenCode, selecionáveis no app.
2. Conversação de voz fluida.
3. ZARA Lab totalmente funcional, se autocodificando, bots conversando 24h.

**Estado (17:50):**
- Causa raiz do "nada muda": o app roda empacotado; mudanças no fonte não
  afetam o exe. Ver `docs/ANALISE_EQUIPE_20260922.md` (análise dos 4 agentes).
- CORRIGIDO e empacotado (BUILD_ID `1f6215aa` em `frontend/release3/win-unpacked`):
  OpenCode CLI com candidatos explícitos + cache fallback; config semeado no
  primeiro boot; chave Gemini com fallback no config; reposição casa na
  availability classificada; fallback/reposição usam `_model_status` (mata o
  deadlock do primeiro turno).
- PROVADO por IPC no exe real (17:43-17:46): codex luna falhou por cota →
  repositioning engatou → MiMo free expirou → **Muse Spark 1.2 free
  COMPLETED** — a ZARA respondeu com modelo gratuito. Engine-list mostra 8
  cérebros OpenCode no seletor.
- Frontend rebuildado: asar com o fix de proveniência (fallback factual
  chega à tela) + instalador novo em `frontend/release/`.
- Commits: 7a65f23, 40222c5, 8dde2d8, 8ca5d10, c8a9987 (branch
  lab/autonomia-20260911). `.claude/` restaurada do git.

**Pendente para o Alex (20:00):** teste físico de voz (G3 — fala e ouve) e
aprovação visual do seletor. Voz: Gemini Live depende da chave (env User
level SETADA; portão com fallback no config).

## Objetivo anterior — MISSÃO JARVIS (2026-09-05, decisão do Alex: opção B)

Alex substituiu a prioridade operacional. A interface (Titanium Emerald) está
congelada e aprovada — não é mais missão de redesign. A missão agora é
transformar a casca visual pronta em assistente real, nesta ordem de
dependência (não commits isolados):

```
1. CONVERSAÇÃO  2. AÇÕES  3. VOZ  4. APPS  5. MEMÓRIA  6. APRENDIZADO  7. AUTONOMIA
```

O backlog antigo de voz (F1.1 Kore → F1.2 Latência → F1.3 Microfone → F1.4
Voz→Ação) **deixa de controlar sozinho a ordem global**, mas não foi
descartado: o trabalho já feito em voz Kore é preservado e será integrado
quando a missão chegar na camada Voice (item 3), sobre a fundação
Text/Voice → Context → Planner → ToolRouter → Execution → Verification →
Response/UI/TTS.

Build ativo (`ZARA_ACTIVE_BUILD.json`/`.txt`): instalado em
`C:\Users\alexp\AppData\Local\Programs\zara-frontend\ZARA 3.0.exe` — o mesmo
caminho do atalho padrão do Windows/Start Menu, então abrir "ZARA 3.0" normal
já abre este build. BUILD_ID `release-candidate-windowfix-20260905-2224`,
GIT_COMMIT `4f415e6` (dirty). Gerado por `tools/build_candidate.py` (troca de
sidecar sobre o frontend de `.current-build-staging-20260905-204831`).

**Golden path P0 — TESTADO NO BUILD EMPACOTADO em 2026-09-05, todos passando:**
- "Oi Zara" → resposta real ("Oi, Alex. Como posso ajudar você agora?") — CORRIGIDO nesta sessão (estava dando erro "No text provided")
- "Abra a Calculadora" → **fora de escopo por decisão do Alex** (`ZARA-APPS-REAIS-2026-08-27`): ele tirou a calculadora da lista de apps de propósito. Não reintroduzir.
- "Quanto de RAM estou usando?" → resposta cita a métrica real (~45% de 16GB medido); a frase vem com um preâmbulo estranho sobre "créditos de API" que não faz sentido — QUALIDADE, não bloqueio, ver TASK_BOARD
- "Abra o Chrome" → abre e Chrome aparece na lista de processos — já funcionava
- "Minimize o Chrome" → minimiza e `IsIconic` confirma — CORRIGIDO nesta sessão (só existia minimizar a janela ativa, não por nome de app)

Evidência: `core/conversation_history.py` (histórico real, não simulado) +
checagem Win32 direta no processo do Chrome. Ver `.claude/TASK_BOARD.md` para
os dois bugs corrigidos e os testes de regressão.

Depois: Windows/PC control amplo → browser/arquivos → microfone/STT → Voice
Kore/TTS → barge-in → apps desktop dentro da ZARA → memória/Obsidian →
rotinas.

Modelo de trabalho mantido: `ORG.md` (Chief of Staff = esta sessão) +
`WORKING_MODEL.md`. Não existe uma segunda organização Opus/Sonnet paralela —
quando análise/arquitetura difícil pedir um "segundo par de olhos", delega-se
via subagente real (Agent tool), nunca fingindo que Sonnet é Opus.

Silêncio operacional total durante a missão (ver `WORKING_MODEL.md`): só
interromper por decisão irreversível, risco alto ou blocker externo genuíno.

## Task ativa

T-JARVIS-P0-01 — ver `TASK_BOARD.md`.

## Owner da task

Chief of Staff (sessão principal), delegando por área conforme necessário.

## Files

`core/ipc_handlers.py`, `core/action_registry.py`, `core/pc_voice_intent.py`,
`core/actions/*`, `frontend/src/renderer/components/zara-home/TextCommandInput.tsx`.

## Dependencies

Nenhuma pendência externa conhecida no momento da abertura desta missão.

## Status

`IN_PROGRESS`.

## Next action

Fase 0 e o golden path P0 de texto+ação estão fechados e verificados no build
empacotado (ver acima). Próximo: ampliar PC control (Fase 2 da missão —
arquivos, sistema, browser além do que já existe) e só depois destravar Voice
(reaproveitando o trabalho Kore já feito). Ver `TASK_BOARD.md` para a tarefa
aberta e os itens de qualidade/limpeza pendentes.








### Acréscimo de evidência automatizada — 2026-09-23
- No candidato F1 nomeado, o comando de voz reduziu o volume real do Windows de 30% para 20%, confirmou 20% por leitura independente e restaurou o nível de teste; o volume final voltou a 98%, sem mudo. Evidência: `PACKAGED_RUNTIME`.
- A resposta chegou ao renderer, mas não foi aprovada como reprodução completa. O trace `BARGE_IN` vem do evento `server_content.interrupted` do Gemini Live (o comando reconhecido não é uma ordem de parar); o executor marcou `TTS_ABORT`. A causa da interrupção segue **NÃO PROVADA**, pois o teste usou microfone simulado e não registrou a configuração real de AEC.
- Nenhum código foi alterado nesta investigação. P1.4/P1.5, comparação física P1.6 e aprovação de voz P1.7 continuam pendentes.
- Os dois perfis temporários gerados pelos testes foram movidos, sem exclusão, para `_quarentena/organizacao-2026-09-23/voz-testes-runtime/controle-20260923/`; manifesto e tamanhos estão registrados em `manifest.json`.

### Provas adicionais no EXE F1 — controles reais (2026-09-23)
- `PACKAGED_RUNTIME`: voz “diminua o volume” reconhecida; volume do Windows 30%→20%, leitura confirmou 20%, restauração confirmou 30%; estado final global 98%, sem mudo. Resposta Kore foi cortada por `server_content.interrupted`; áudio completo não provado.
- `PACKAGED_RUNTIME`: no caminho de texto, abrir, minimizar e fechar uma janela de Notepad criada pelo teste. A janela apareceu; `IsIconic=true` após minimizar; o processo do Notepad encerrou após o comando de fechar. Nenhuma janela anterior existia; a janela de teste foi fechada.
- Após o backend estar pronto, o comando para abrir Notepad respondeu em 1.62 s; na sequência abrir/minimizar/fechar respondeu em 2.85 s, 190 ms e 177 ms. São amostras individuais, não medianas.
- A inicialização fria do backend levou 17.4 s em um probe e 37.8 s em outro. Pedidos enviados antes da prontidão esperaram 17.1–19.3 s; esses tempos incluem a inicialização e não medem só a execução do comando. A causa interna dessa variação não foi isolada.
- Áudio, mudo e brilho em controles de texto já têm relatório empacotado anterior; os alvos testados foram restaurados. Isto não cobre todas as famílias de controle.
- Perfis e logs isolados foram movidos para `_quarentena/organizacao-2026-09-23/voz-testes-runtime/`, cada conjunto com manifesto. Nenhum arquivo foi apagado.

**Ainda aberto:** Kore sem corte e buffer de áudio (`P1.4/P1.5`), comparação física de latência (`P1.6`), aprovação de voz do Alex (`P1.7`), inventário restante de F0, demais famílias de PC e todas as fases F2–F4.

### Evidência adicional — entrada de texto e probe de saída (2026-09-23)
- No EXE F1, a rota normal de conversa abriu o Notepad, digitou `ZARA_TEST_20260923_DIGITACAO`, teve o conteúdo lido pela UI Automation do Windows, desfez a digitação e fechou o processo criado pelo teste. Clipboard original preservado. Perfil isolado em quarentena com manifesto. Evidência `PACKAGED_RUNTIME`, não cobre todas as ações do PC.
- Tempos após prontidão: abrir 1.977 ms; digitar 335 ms; desfazer 218 ms; fechar 153 ms. Backend frio: 15.813 ms, observação única.
- O primeiro probe de loopback expirou antes de iniciar captura; resultado do handshake Gemini NÃO CONFIRMADO e nenhum sinal capturado naquela tentativa. Não há prova para afirmar que não houve chamada Gemini.
- Na repetição v2 do mesmo candidato, áudio sintético pelo microfone falso foi reconhecido (“quanto é 2 + 2?”); resposta direta “São quatro” entregou 15 blocos Kore ao renderer. 15 fontes terminaram naturalmente e o loopback Stereo Mix captou janela contínua não silenciosa de 2,72 s. O relatório estruturado registra 0 underruns, 0 BARGE_IN e 0 TTS_ABORT. Isto prova sinal digital no caminho do Windows, não inteligibilidade nem audição humana. O wrapper forçou AEC, supressão de ruído e AGC efetivos em true; não representa as constraints normais do app.
- Latência observada: 7,17 s entre LISTENING e primeiro áudio; estimativa grosseira de 3,84 s entre fim da fala sintética e primeiro áudio. Uma amostra, não medição oficial nem antes/depois. P1.4 parcial; P1.5 não provado; P1.6/P1.7 pendentes.
- No build-base release-candidate-f1-voz-20260923-114336, o teste da janela ativa passou, mas “Maximize o Bloco de Notas” por nome falhou. Este gap foi corrigido e passou no candidato ativo release-candidate-f1-notepad-control-20260923-1703; o teste de nomeado inclui max/min/restore com readback Win32 independente. Ver a atualização operacional abaixo.
- Nova prova PACKAGED_RUNTIME de arquivos: ZARA criou uma pasta vazia temporária em Downloads; leitura independente confirmou a pasta; ela foi movida para _quarentena com manifest, e o caminho original ficou ausente. A rota correta devolve engine=file_control. Tempo da ação 1,638 ms após readiness; backend frio 17,664 ms. Relatório .unlazy/zara-master-20260923/pc-controls/files-create-folder-real-report.json.
- O volume continua restaurado a 98%, sem mudo.


## Atualização operacional — controle de janelas nomeadas (2026-09-23)

- Candidato ativo: release-candidate-f1-notepad-control-20260923-1703, derivado do build completo F1 release-candidate-f1-voz-20260923-114336 pelo tools/build_candidate.py. EXE: frontend/release-candidate-f1-notepad-control-20260923-1703/win-unpacked/ZARA 3.0.exe. EXE SHA256: 67DC2A7036860A68E5312C212C31B8772AC463ED0289FCC44897867F55075E89; backend SHA256: 696BEF30954613E5AD9BAAFAD7FFC5D9ECF8DA9FB5ADC5A7791EECE83691994D; ASAR SHA256: 2E2DA47E5D6F2781AC86F24227B98B14EEC214BCCF26BF406AF49811C5B5623C. O EXE e ASAR mantêm os hashes do candidato base; a nova identidade de backend distingue esta troca de sidecar.
- PACKAGED_RUNTIME: 48 testes focados de controle de janela passaram após 5 falhas reproduzidas antes do patch. No EXE nomeado, ZARA abriu um Notepad de teste e as rotas “Maximize o Bloco de Notas”, “Restaure o Bloco de Notas”, “Minimize o Bloco de Notas” e nova restauração mudaram os estados Win32 para IsZoomed=true, IsZoomed=false, IsIconic=true e IsIconic=false/IsZoomed=false. A ação de fechar encerrou o processo de teste. Tempos individuais após o backend ficar pronto: 226,5 / 292,6 / 177,8 / 205,3 ms. Readiness fria do perfil isolado: 18,618 s; não é latência de voz.
- Relatórios: .unlazy/zara-master-20260923/pc-controls/notepad-named-target/packaged-smoke-report.json e new-app-opened.json. Perfil e logs isolados preservados com manifest em _quarentena/organizacao-2026-09-23/voz-testes-runtime/controle-notepad-named/<BUILD_ID>/.
- O app está aberto neste candidato, PID 1264, janela “ZARA 3.0 — Neural Interface”, Responding=true. Evidência de abertura é PACKAGED_RUNTIME; não prova interação física de voz.
- F1 permanece aberta. A aprovação física da fala por Alex (P1.7), a medição física comparável (P1.6), a validação de saída de voz (P1.4/P1.5) e os gates restantes de F0 continuam pendentes. F2–F4 não foram concluídas nem promovidas.
- O sidecar foi construído do snapshot backend atual do worktree sujo, que contém mudanças pré-existentes em várias áreas. Este smoke prova os controles nomeados do Notepad e não certifica os demais deltas já presentes na árvore.
