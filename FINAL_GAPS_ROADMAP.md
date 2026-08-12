# FINAL GAPS ROADMAP

Task: `ZARA-CORUJAO-FINAL-GAPS-002`
Atualizado: 2026-08-11
Regra: uma tarefa ativa por vez; `PHYSICAL_BY_ALEX` nunca e inferido de teste automatizado.

## P0-A — Voz fisica

TASK: preparar wake word, mic -> intent -> action, barge-in, self-listening, action layer compartilhada e diagnosticos.
PRIORITY: P0
STATUS: AUTONOMOUS_DONE / AWAITING_ALEX_PHYSICAL
SOURCE: pipeline localizado por Graphify em `core/voice_stt.py`, `core/gemini_live_voice.py`, `core/voice_tts.py`, `core/ipc_handlers.py` e `core/pc_voice_intent.py`; local pipeline agora inicia atras do wake gate, pausa reconhecimento durante TTS e interrupt para TTS+STT.
TEST: PASS — 11 testes de voz focados + 3 provas de action layer compartilhada; `py_compile` PASS.
RUNTIME: READY_NOT_PHYSICAL — microfone default e modelo Vosk presentes; wake detector real carregou `zara/sara`; Gemini key configurada; sessao de microfone nao foi iniciada.
PHYSICAL_BY_ALEX: AWAITING_ALEX_PHYSICAL
READBACK: `wake_detector_ready=true`, `wake_word_enabled=true`, `gate_open=false`; diagnostico sanitizado incluido em `voice-status`.
BLOCKER: barge-in por voz durante a propria fala requer prova fisica; o interrupt explicito agora interrompe TTS+captura. Kokoro local nao possui pesos, mas Gemini Live esta configurado.
NEXT: P0-B. Roteiro Alex: “Zara, quem e voce?”; “Zara, volume em 20%”; “Zara, toque Hotel California”; “Zara, pause”; “Zara, continue”; “Zara, abra Downloads”; “Zara, me lembre de testar a voz daqui a dois minutos”; interromper uma resposta; confirmar que a voz da propria ZARA nao gera novo comando.

## P0-B — Reminder visivel + UTF-8

TASK: parse, persistencia, same-ID, timer, uma notificacao e texto integro.
PRIORITY: P0
STATUS: AUTONOMOUS_DONE / AWAITING_ALEX_PHYSICAL
SOURCE: PARTIAL anterior.
TEST: PASS — 26 backend reminder tests + 2 frontend normalization tests; TypeScript test compile PASS.
RUNTIME: PASS_BACKEND — scheduler real produziu exatamente 1 evento, mesmo ID, estado FIRED e codepoints UTF-8 integros.
PHYSICAL_BY_ALEX: AWAITING_ALEX_PHYSICAL para avaliacao visual.
READBACK: `same_id=true`, `event_count=1`, `unicode_equal=true`, `state=FIRED`; Electron envia toast interno e notificacao nativa apenas quando a janela nao esta focada.
BLOCKER: aparencia do toast/notificacao continua sem prova fisica de tela.
NEXT: P1-A.

## P1-A — Janelas completas

TASK: focus, switch, minimize, maximize, restore, move, resize e close seguro por HWND.
PRIORITY: P1
STATUS: AUTONOMOUS_DONE
SOURCE: focus nomeado existente preservado; adicionados move esquerda/direita, resize maior e close contextual por HWND exato. Alternancia cega foi bloqueada e agora exige alvo nomeado.
TEST: PASS — 46 testes focados de janela/contexto; `py_compile` PASS. Fragilidade de fixture via `__new__` sem estado efêmero do clipboard classificada como `KNOWN_TEST_DEBT` e corrigida defensivamente sem alterar o runtime normal.
RUNTIME: PASS — janela descartavel do Bloco de Notas: HWND 32376058 inequivoco; focus, move-right, resize, minimize, maximize, restore e WM_CLOSE todos confirmados por readback Win32. A janela foi fechada ao final.
PHYSICAL_BY_ALEX: N/A para a prova automatica Win32; voz fisica continua coberta pelo roteiro P0-A.
READBACK: move `(156,156,1596,909) -> (960,0,1920,1032)`; resize `-> (288,0,1632,1032)`; estados `restored -> minimized -> maximized -> restored`; `IsWindow=false` apos close.
BLOCKER: `troque de janela` sem nome agora responde pedindo alvo explicito; ZARA Room/ChatGPT e protegida contra close.
NEXT: P1-B.

## P1-B — Browser util

TASK: scroll, leitura, resumo, fechar aba e avancar com postcondition em browser separado.
PRIORITY: P1
STATUS: AUTONOMOUS_DONE
SOURCE: scroll por UI Automation com percentual antes/depois; leitura/resumo somente de `Document`; close-tab exige >=2 abas e redução confirmada; back/forward exigem mudança real de título. ZARA Room protegida em todas as ações do bloco.
TEST: PASS — 49 testes focados de mídia/router; `py_compile` PASS. Dívida da fixture de router também foi eliminada defensivamente; conjunto ampliado P1-A/router ficou 61 PASS.
RUNTIME: PASS — Chrome descartável com perfil isolado, sem login/cookies principais e accessibility forçada. Scroll down `0 -> 2.332%`, scroll up `2.332 -> 0`; leitura real 336 caracteres; resumo gerado depois do conteúdo; back/forward confirmados por títulos; close-tab `2 -> 1` com janela viva.
PHYSICAL_BY_ALEX: N/A para runtime automatizado; voz física continua AWAITING_ALEX no P0-A.
READBACK: `CONTENT_READ`, `verified=true`; `window_alive=true`; títulos Página Dois -> Página Um -> Página Dois em back/forward.
BLOCKER: URL da página local não foi exposta pelo address bar UIA, então ficou vazio em vez de ser inventado. Perfis isolados foram encerrados; remoção automática das pastas temporárias foi bloqueada pela política da ferramenta.
NEXT: P1-C input/produtividade.

## P1-C — Input/produtividade

TASK: type_text, hotkeys allowlisted, copy, paste, select-all seguro e Task Manager.
PRIORITY: P1
STATUS: AUTONOMOUS_DONE / TASK_MANAGER_CLOSE_BLOCKED_PRIVILEGE
SOURCE: `input_type_text` Unicode com clipboard temporário restaurado; `input_hotkey` usa allowlist fechada; campo focado exige UIA Edit/Document, mesmo PID/HWND e bloqueia senha/login/pagamento/admin/terminal/shell de agente.
TEST: PASS — 45 testes de input, clipboard, open-app e close-app; `py_compile` PASS.
RUNTIME: PASS input — WOW_TEXT_FLOW RUNTIME_PROVEN_IN_ISOLATED_CHROME_FIELD: type, Ctrl+A, copy, replace-all e paste; resultado final exato por codepoints, incluindo `ó/ç/ã`, e clipboard original restaurado. Task Manager OPEN RUNTIME_PROVEN com PID/HWND criados nesta prova.
PHYSICAL_BY_ALEX: NOT_PROVEN por voz.
READBACK: texto final igual ao esperado; lengths `0→53`, seleção/cópia, replace `53→18`, paste `18→71`; Task Manager PID 4080/HWND 3736404.
BLOCKER: Task Manager abriu elevado; WM_CLOSE, Stop-Process sem elevação, UIA Close e Alt+F4 exato foram recusados/ineficazes. Não elevar privilégios. A instância de teste permanece aberta para fechamento manual.
NEXT: P1-D áudio/mídia global.

## P1-D — Audio/midia global

TASK: sessao atual, play/pause/resume/next/previous/metadata/volume/default device.
PRIORITY: P1
STATUS: AUTONOMOUS_DONE / GLOBAL_TRANSPORT_AWAITING_SESSION
SOURCE: YouTube Tier-S preservado; global WM_APPCOMMAND continua falhando honestamente sem mudança semântica; adicionado `audio_status` real por pycaw para endpoint padrão, volume, mute e sessões ativas. Rota absoluta de volume foi antecipada para não colidir com o genérico “coloque <música>”.
TEST: PASS — 43 testes focados de áudio, mídia e contexto de volume; `py_compile` PASS.
RUNTIME: PASS status — saída padrão `Altofalantes (Realtek(R) Audio)`, volume 88%, mudo, nenhuma sessão render ativa. Volume/mute já tinham PHYSICAL_PROOF anterior e não foram alterados novamente.
PHYSICAL_BY_ALEX: play/pause/next/previous global aguardam uma sessão de mídia real; YouTube semântico permanece separado.
READBACK: endpoint ID real, `active_render_sessions=[]`, `metadata_backend=NOT_AVAILABLE`.
BLOCKER: `winsdk`/`winrt` ausentes; sem sessão ativa não há metadata nem transição global a provar. Troca de dispositivo padrão classificada `NOT_SUPPORTED_SAFE` (não usar COM PolicyConfig não documentado).
NEXT: P1-E informações reais do PC.

## P1-E — Informacoes reais do PC

TASK: bateria, rede, adaptadores, dispositivos, CPU, RAM, disco, processos, uptime e audio.
PRIORITY: P1
STATUS: AUTONOMOUS_DONE
SOURCE: `system_info` ampliado com uptime, bateria real, energia, adaptadores/status de rede e disco do sistema; CPU/RAM/disco/processos existentes preservados.
TEST: PASS — 2 testes focados de informações reais; `py_compile` PASS.
RUNTIME: PASS — Windows 10 build 22621; uptime 16.873s; bateria 100% ligada à energia; Wi-Fi UP 117 Mbps; CPU 11,2%; RAM 57,4%; disco C: 95,1%; 158 processos; áudio real coberto no P1-D.
PHYSICAL_BY_ALEX: N/A
READBACK: read-only estruturado; bateria ausente seria `null`, nunca sucesso inventado.
BLOCKER: disco C: com apenas ~12,46 GB livres (95,1% usado) é condição real a observar; nenhuma limpeza automática autorizada.
NEXT: P1-F visão/screenshot útil.

## P1-F — Visao/screenshot util

TASK: verificar backend local/gratuito para interpretacao basica da tela.
PRIORITY: P1
STATUS: AUTONOMOUS_DONE / GENERAL_INTERPRETATION_BLOCKED_BACKEND_NOT_AVAILABLE
SOURCE: captura de tela local existente preservada; PIL, `mss`, `pytesseract` (modulo) e OpenCV importam. O executavel Tesseract nao esta instalado/no PATH e nenhum backend geral de visao local autorizado foi encontrado.
TEST: PASS — 5 testes focados de screenshot/notificacao; `py_compile` de `core/actions/vision.py` PASS.
RUNTIME: SCREENSHOT_CAPTURE RUNTIME_PROVEN — regiao exata da janela do Task Manager capturada por HWND em PNG 780x590. GENERAL_SCREEN_INTERPRETATION BLOCKED_BACKEND_NOT_AVAILABLE.
PHYSICAL_BY_ALEX: NOT_PROVEN
READBACK: arquivo PNG local valido; UI Automation semantica continua disponivel para controles suportados, mas nao foi reclassificada como interpretacao visual geral.
BLOCKER: backend geral local/gratuito ausente. Por ordem do Mentor, nao instalar Tesseract, infraestrutura pesada ou servico externo e nao prender a fila.
NEXT: P2-A Jarvis 5/5.

## P2-A — Jarvis 5/5

TASK: plano pratico de cinco etapas e um composto WOW somente com primitives runtime-proven.
PRIORITY: P2
STATUS: AUTONOMOUS_DONE
SOURCE: o planner compartilhado entre texto e voz ganhou dois dominios deterministas (`downloads` e `status_pc`) e continua limitado a cinco etapas, usando somente os executores existentes com gates/readback proprios. Import frio do action registry foi tornado explicito antes do preflight.
TEST: PASS — 19 testes focados de Jarvis, composto, intents do sistema e informacoes reais; `py_compile` PASS. O teste pratico confirma exatamente `5/5` e a ordem das primitives.
RUNTIME: PASS 5/5 — comando real: abrir projeto, abrir Downloads, ler estado do PC, recuperar pendencias e persistir lembrete para dois minutos. Resultado consolidado `Plano Jarvis concluido: 5/5`; CPU/RAM/disco/processos reais, pendencias locais e mesmo lembrete `SCHEDULED` confirmados.
PHYSICAL_BY_ALEX: NOT_PROVEN
READBACK: 1 Projeto solicitado ao Explorer; 2 Downloads solicitado ao Explorer; 3 Estado do PC `CPU 13,1% / RAM 58,0% / disco 94,4% / 155 processos`; 4 pendencias do Catalogo Vivo; 5 lembrete com mesmo texto e ID persistido. Nenhum novo HWND do Explorer ficou aberto.
BLOCKER: voz/microfone fisico continua AWAITING_ALEX; o 5/5 desta fase e RUNTIME do pipeline deterministico compartilhado, nao PHYSICAL_BY_ALEX.
NEXT: P2-B LAB/Mission Control.

## P2-B — LAB/Mission Control

TASK: mensagens, propostas, tasks, persistencia, fila, assignment, respostas, UTF-8, membros e historico reais.
PRIORITY: P2
STATUS: AUTONOMOUS_DONE / EXTERNAL_EXECUTORS_TRUTHFULLY_LIMITED
SOURCE: LAB preserva SQLite, ordem por `created_at + rowid`, propostas/Approval Gate, Autonomy Core e relays. Roster agora inclui os nove membros pedidos; Codex aparece como `NOT CONFIGURED` e nao pode ser selecionado para chat/execucao enquanto nao existir ponte local real. O frontend desabilita qualquer membro sem `can_chat`.
TEST: PASS — 46 testes focados de LAB, persistencia, roteamento, OpenCode relay, Memory Galaxy, single-writer e Room relay; `py_compile` PASS; frontend `tsc --noEmit` PASS.
RUNTIME: PASS isolado — duas mensagens consecutivas e duas respostas ZARA persistiram na ordem apos novo `LabCoordinator`; texto, resposta e resumo UTF-8 tiveram igualdade exata. Proposta LOW passou DISCUSSION -> APPROVED; task persistente entrou QUEUED. Heartbeat de worker `development` e `claim_next` atribuíram a mesma task e o readback mudou para PLANNING com `assigned_worker` exato.
PHYSICAL_BY_ALEX: NOT_PROVEN
READBACK: roster exato `alex,zara,mentor,codex,hermes,opencode,openclaw,cline,aider`; Codex NOT CONFIGURED, Hermes OFFLINE e Mentor EXTERNAL no runtime isolado. Approval Gate ON; execução externa permanece LOCKED; task claimada apenas no banco isolado, sem editar producao.
BLOCKER: nenhuma ponte Codex local; Hermes/Mentor podem ficar OFFLINE/EXTERNAL; OpenCode real continua sem `can_execute`. O LAB nao mostra esses agentes como ONLINE nem inventa respostas.
NEXT: P3-A Smart Router/conversa.

## P3-A — Smart Router/conversa

TASK: rota, cooldown, fallback, provider morto, continuidade, memoria e conversa natural.
PRIORITY: P3
STATUS: AUTONOMOUS_DONE
SOURCE: AUTO SMART/ECONOMY preservam zero-cost eligibility, health por provider/model, cooldown para 429/quota, bloqueio de 401/403, uma cadeia com diversidade de provider e historico explicito. Memoria operacional, ConversationHistory e autoconhecimento permanecem separados.
TEST: PASS — 78 testes focados de failover, integridade do router, prompt conversacional, contexto operacional, recall, historico e autoconhecimento; `py_compile` PASS.
RUNTIME: PASS — duas chamadas reais gratuitas via AUTO ECONOMY. Primeira resposta nao vazia por `gemini_36_flash`; segunda por fallback/roteamento `gemini_35_flash_lite` recebeu o historico e respondeu exatamente `Orion`, comprovando continuidade entre turnos.
PHYSICAL_BY_ALEX: NOT_PROVEN
READBACK: politica `economy`; ambos os providers/models retornaram sem erro; `continuity_exact=true`. Status local mostrou nove modelos gratuitos configurados entre NVIDIA, Groq e Gemini, sem imprimir chaves.
BLOCKER: disponibilidade externa continua sujeita a quota/rede; os testes cobrem 401/429/timeout/5xx e cooldown, mas nenhuma falha real foi provocada contra o servico.
NEXT: P3-B estabilidade/soak.

## P3-B — Estabilidade/soak

TASK: Boot/Home, Electron, sidecar, Supercerebro, gateway, providers, memoria, contexto e reminders.
PRIORITY: P3
STATUS: AUTONOMOUS_DONE
SOURCE: build candidata gerada com `tsc + vite build + tsconfig.node`; lifecycle Electron preserva single-instance e encerra o sidecar por EOF antes do kill de contingencia.
TEST: PASS — build frontend e Electron PASS; testes finais direcionados listados no RESULT final.
RUNTIME: SHORT_SOAK PASS — uma unica ZARA dev real ficou ativa por aproximadamente dois minutos. Home/renderer carregou com titulo `ZARA 3.0 — Neural Interface`; sidecar ficou READY; historico local reapareceu (200 mensagens retornadas); Reminder Core e LAB inicializaram; nove providers gratuitos apareceram AVAILABLE; gateway Hermes respondeu `connected=true`, `enabled=false` de forma estavel; 28+ ciclos de metricas/status ocorreram sem restart. LONG_DURATION_STABILITY: AWAITING_FUTURE_VALIDATION.
PHYSICAL_BY_ALEX: NOT_PROVEN
READBACK: exatamente um Electron raiz, seus tres subprocessos normais, um launcher Python e um worker Python; IDs permaneceram os mesmos nos dois checkpoints. `startup timeout=0`, `reconnect=0`, `Traceback=0`, `Unhandled=0`. Fechamento por HWND foi verificado; cinco segundos depois havia `0` processos Electron/sidecar da ZARA e o Vite criado para o teste tambem estava encerrado.
BLOCKER: Supercerebro nao foi ativado fisicamente durante o soak; apenas gateway conectado e estado OFF coerente foram provados. Microfone/voz continuam AWAITING_ALEX_PHYSICAL.
NEXT: relatorio final e handoff para Alex/Mentor.

## Fora da fila

Paint, Calculadora, Edge, Spotify app ausente, apps raros, cosmetica e long tail: SKIPPED_BY_SCOPE.
Calendar/email: BLOCKED_NOT_CONNECTED.
Mentor Relay Issue #5: DEFERRED.
OpenCode: DEFERRED.
Delete/power: BLOCKED_SAFETY; nao executar fisicamente.
