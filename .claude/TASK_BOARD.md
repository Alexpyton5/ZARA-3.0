# ZARA — Task Board
## PLANO MESTRE ATIVO — aprovado por Alex em 2026-09-23

- ID: F0-P0.1-20260923
  status: PARTIAL_WITH_INVENTORY
  evidência: 75 itens originais movidos (8.10 GB). Mais 5.50 GB de staging duplicado preservado está separado no manifesto. Auditoria: nenhum stub comentado encontrado em core e o manifest não tem entrada de stub; isso prova só “não encontrado em core”, não ausência repo-wide dos 35. Nenhum banco/memória viva de usuário foi movido. core/memory e memory_system foram arquivados como código-fonte, preservados porque podem ser úteis; registros de memória morta não foram encontrados nem classificados. Nada apagado; nenhum espaço físico liberado.
- ID: F0-P0.2-20260923
  status: DONE_WITH_SOURCE_IDENTITY_UNVERIFIED
  evidência: ponteiro e BUILD_INFO identificam exatamente o pacote instalado e seus três hashes. O app.asar instalado corresponde a `release2`; o backend não corresponde a nenhum dos três pacotes disponíveis. Não chamar de build validado.
- ID: F0-P0.3-20260923
  status: EXECUTED_RED
  evidência: 2,399 passed / 18 failed / 32 skipped / 1 deselected. Um teste de localização obsoleto foi atualizado e seus 2 testes passaram isoladamente. Permanecem 16 falhas em Lab/build com arquivos sujos antes da tarefa e 1 falha de voz já conhecida. Relatório em `_quarentena/organizacao-2026-09-23/VALIDATION_P0.3.md`.
- ID: F1.1-VOICE-DIRECT-20260923
  status: SOURCE_AND_TEST_DONE_PACKAGED_DIRECT_ROUTE_PASS_PHYSICAL_PENDING
  owner: Chief of Staff (sessão principal; `core/ipc_handlers.py`)
  objetivo: P1.1: habilitar conversa direta Gemini Live e manter intents no executor.
  evidência: SOURCE + 58 testes focados aprovados. A anotação antiga de ASAR sem patch referia-se a outro candidato e foi superada por `release-candidate-f1-voz-20260923-114336`: conversa sintética em pt-BR reconhecida, resposta direta em Kore e 16 blocos de áudio entregues ao renderer. Completar a reprodução no alto-falante e aprovação física ainda pendentes.
- ID: F1.2-VOICE-REDUNDANT-20260923
  status: SOURCE_EXISTING_BEHAVIOR_VERIFIED
  evidência: Gemini Live descarta a geração de voz em turnos de executor e envia execução no primeiro frame completo de texto. Sem patch dedicado.
- ID: F1.3-COST-GATED-TTS-20260923
  status: SOURCE_PATCHED_AND_FOCUSED_TESTS_PASS
  owner: Chief of Staff (`core/ipc_handlers.py`)
  evidência: Kore Live e fallback Gemini HTTP só são permitidos quando o cérebro foi provado grátis. O teste `test_cerebro_nao_gratis_nao_faz_segunda_viagem_de_tts_ao_gemini` passou junto de três regressões focadas de fallback/interrupt em `tests/test_voice_tts_cascade.py` (4 passaram, 19 deselected). Isso prova source/test, não disponibilidade de modelos no app.
- ID: F1.4-KORE-BUFFER-20260923
  status: DIAGNOSTIC_PLUS_SYNTHETIC_LOOPBACK_PARTIAL_PHYSICAL_PENDING
  owner: Chief of Staff (`frontend/src/renderer/lib/aecAudio.ts`)
  evidência: instrumenta intervalo/duração/tempo em fila e underrun; não altera buffer/reprodução. Precisa de áudio real para determinar causa e provar eventual correção. 11 testes renderer passaram; nenhum teste físico ainda.
- ID: F1.5-SINGLE-VOICE-FALLBACK-20260923
  status: SOURCE_AND_FOCUSED_TESTS_PASS_PACKAGED_FALLBACK_NOT_EXERCISED
  evidência: impede reiniciar frase em outra voz após primeiro áudio Kore; mantém fallback se Kore falhar antes de qualquer áudio. `test_kore_parcial_nao_troca_de_voz_no_meio_da_frase`, `test_falha_da_kore_antes_do_primeiro_audio_ainda_usa_edge` e `test_interromper_a_kore_nao_faz_outra_voz_recomecar` passaram. O smoke empacotado concluiu a resposta Kore sem fallback; portanto o fallback real não foi exercitado.
- ID: F1.6-VOICE-LATENCY-20260923
  status: HISTORICAL_BASELINE_ONLY_AFTER_BUILD_PENDING
  evidência: 3 turnos históricos sem identidade BUILD_ID — mediana 16.726 ms total, 13.897 ms até primeiro áudio entregue; 727 ms pedido TTS→primeiro áudio. Não compara contra source atual. Antes/depois físico ainda pendente.
- ID: F1-PACKAGED-20260923
  status: PACKAGED_RUNTIME_SMOKE_PASS_PHYSICAL_VOICE_PENDING
  evidência: build completo oficial; 100 testes backend focados, 11 renderer e compilação frontend passaram. Sidecar exato respondeu ao comando local em 93 ms; EXE exato permaneceu ativo por 12 s e iniciou sidecar. Identidade e hashes em `ZARA_ACTIVE_BUILD.json`. Kore, buffer limpo e latência percebida não aprovados fisicamente.
- ID: F1-SELF-INTERRUPT-20260923
  status: SOURCE_TEST_AND_PACKAGED_SYNTHETIC_SMOKE_PASS_PHYSICAL_VOICE_PENDING
  evidência: corrigida a interrupção interna do Gemini sem retirar o barge-in real; 2 regressões focadas passaram. Novo build ativo `release-candidate-f1-voice-interrupt-20260923-1756`; EXE/backend/ASAR hashes estão em `ZARA_ACTIVE_BUILD.json`. No EXE isolado: áudio sintético transcrito, volume real do Windows 30%→20% confirmado independentemente, resposta “Volume definido para 20%”, 27 blocos/233.283 bytes Kore ao renderer, 27 fontes WebAudio completadas naturalmente sem `stop()`, 4,64 s de sinal no Stereo Mix, interrupção interna esperada presente no trace e nenhum falso `BARGE_IN`/`TTS_ABORT`. Volume original 98%, sem mudo, restaurado. Relatório `.unlazy/zara-master-20260923/voice-test/server-interrupt-ownership/packaged-smoke-20260923-175746.json`; perfil/logs isolados preservados com manifest em `_quarentena/organizacao-2026-09-23/voz-testes-runtime/server-interrupt-ownership/`. É `PACKAGED_RUNTIME`, não aprovação física.
- Evidência adicional PC (2026-09-23): no mesmo EXE, abrir Notepad, digitar um marcador, ler o campo por UI Automation, desfazer e fechar passaram com pós-condições observadas. Uma execução inicial do harness falhou apenas ao arquivar o perfil; foi descartada. Reexecução isolada passou. Relatório: `.unlazy/zara-master-20260923/pc-controls/notepad-typing-real-report.json`. Buffer, continuação da fala e voz física continuam pendentes.
- Correção do registro do probe inicial: expirou antes da captura; handshake Gemini NÃO CONFIRMADO (não afirmar “nenhuma chamada”). A repetição v2 no mesmo EXE reconheceu a pergunta sintética, respondeu em Kore, entregou 15 blocos ao renderer e o loopback Stereo Mix observou sinal contínuo por 2,72 s; o relatório estruturado registra 0 underruns/BARGE_IN/TTS_ABORT. PACKAGED_RUNTIME restrito a esta conversa: microfone falso e wrapper alterando AEC/ruído/AGC para true; sem prova de inteligibilidade/audição física. Relatório .unlazy/zara-master-20260923/voice-test/packaged-gemini-loopback-v2-report.json; trace termina na rota DIRECT_CONVERSATION e não corrobora sozinho a reprodução.
- Latência v2: 7,17 s entre LISTENING e primeiro áudio; estimativa fala sintética encerrada→primeiro áudio ~3,84 s. Uma amostra sem baseline comparável; P1.6 continua pendente.
- P1.4 fica PARTIAL: houve sinal contínuo e fontes terminaram naturalmente, mas não há escuta/clareza humana nem prova de causa/correção do buffer. P1.5 NÃO PROVADO: fallback não foi acionado. P1.7 físico continua pendente.
- No candidato-base release-candidate-f1-voz-20260923-114336, o comando genérico para janela ativa passou (IsZoomed false→true→false), mas maximizar Notepad por nome falhou. O gap foi corrigido e validado no candidato ativo release-candidate-f1-notepad-control-20260923-1703; ver ZARA-PC-NAMED-WINDOW-NOTEPAD-20260923 abaixo.
- Arquivos no mesmo EXE: frase “Crie uma pasta chamada ZARA_TESTE_PC_20260923_A em Downloads” criou a pasta; readback independente confirmou; foi arquivada sob _quarentena com manifest, sem exclusão. Resposta engine=file_control; ação 1,638 ms após readiness. Relatório .unlazy/zara-master-20260923/pc-controls/files-create-folder-real-report.json.
- Ordem oficial próxima: P1.7 físico no candidato ativo release-candidate-f1-notepad-control-20260923-1703; depois P1.8 exploração; só então F2. Sequência completa na `.claude/CURRENT_MISSION.md`. Lab auto-update inicia OFF; PersonaPlex adiado. KNOWN_BROKEN: P0.1 continua parcial; P0.3 suíte ampla continua vermelha (2,399 passou, 18 falhou); P1.4 sem validação/correção física.


Formato simples. Não virar burocracia.

## DONE

- ID: T-JARVIS-P0-01
  owner: Chief of Staff (sessão principal)
  scope: Fase 0/1 da Missão Jarvis — confirmar fonte↔build↔runtime e validar
    golden path de texto+ação no build empacotado
  files: `core/ipc_handlers.py`, `core/pc_voice_intent.py`, `core/actions/os_ops.py`,
    `tests/test_conversation_history.py`, `tests/test_window_control.py`,
    `ZARA_ACTIVE_BUILD.json`/`.txt`, `ZARA_MASTER_CONTEXT.md`
  DoD: PACKAGED_RUNTIME — testado no app empacotado de verdade (não só pytest):
    - "Oi Zara" → resposta real, gravada em `conversation_history.sqlite3`
    - "Abra o Chrome" → `chrome.exe` real na lista de processos
    - "Quanto de RAM estou usando?" → métrica real na resposta
    - "Minimize o Chrome" → `IsIconic`=True confirmado via Win32 no processo do Chrome
  bugs corrigidos (com teste de regressão cada um):
    1. `handle_send_message` tratava "Oi Zara" sozinho (saudação+nome sem
       comando, `_canonical_request` esvazia) como texto vazio → "No text
       provided". Agora cai de volta no texto bruto quando a canonicalização
       esvazia algo que não estava vazio.
    2. `window_minimize`/`maximize`/`restore` só aceitavam a janela
       ativa/contextual — "Minimize o Chrome" (por nome, não em foco) caía em
       "ainda não sei fazer". Agora resolvem o alvo por nome do mesmo jeito
       que `window_focus_named` já fazia.
  fora de escopo por decisão do Alex: "Abra a Calculadora" — ele tirou
    calculadora da lista de apps em 2026-08-27, não reintroduzir.
  incidente registrado: `frontend/release/` foi sobrescrito ao rodar
    `npm run electron:build` sem override de output — ver `.claude/DECISIONS.md`.
    Builds seguintes usaram `tools/build_candidate.py` (correto, não toca release/).

- ID: T-2026-09-04-01
  owner: Chief of Staff
  scope: instalar modelo de operação permanente (Chief of Staff + hierarquia)
  files: `.claude/ORG.md`, `.claude/WORKING_MODEL.md`, `.claude/CURRENT_MISSION.md`, `.claude/TASK_BOARD.md`, `.claude/DECISIONS.md`
  DoD: 5 arquivos criados e preenchidos, boot order registrado, checkpoint git feito

- ID: T-2026-09-04-00
  owner: (sessão anterior)
  scope: menu `ZARA_INICIAR.bat` + estado verificado `ZARA_STATE.md`/`json`
  files: `ZARA_TESTAR_TUDO.bat`, `ZARA_INICIAR.bat`, `tools/zara_selftest.py`
  DoD: commit `1745a29` — feito e enviado (push) para
  `backup/estado-20260820-1143`

## REVIEW

—

## BLOCKED

—

## IN PROGRESS

- ID: T-JARVIS-P0-02
  status: SUSPENDED_BY_OWNER_PLAN_2026-09-23 (preserved, not canceled)
  owner: Chief of Staff (sessão principal)
  scope: PC control amplo (janelas, sistema, arquivos, browser) — avançando
    incrementalmente: achar gap real via teste → corrigir → regressão →
    rebuild → verificar no build empacotado → commit
  files: `core/actions/*`, `core/pc_voice_intent.py`, `core/file_voice_intent.py`,
    `core/ipc_handlers.py`
  progresso nesta sessão (cada um com teste de regressão; testado no build
    empacotado real, não só pytest):
    1. Fix: "Oi Zara" sozinho virava erro "No text provided".
    2. Fix: minimizar/maximizar/restaurar por NOME de app (só "Chrome" —
       extensível a vscode/zara/projeto, mesma resolução já existente).
    3. Novo: `files_create_folder` — "crie uma pasta chamada X em Downloads/
       Documentos" não existia.
    4. Fix: "abra a área de trabalho" só casava com acento e artigo "a" —
       "area de trabalho" (sem acento) e "abra o desktop" caíam em "ainda
       não sei fazer".
    5. Fix: "vá AO youtube" não era reconhecido (só "vá PARA o youtube"),
       quebrando o comando composto de 3 etapas do próprio exemplo
       golden-path da missão ("Abra o Chrome, vá ao YouTube e pesquise
       Hans Zimmer").
    6. Fix: "Volte."/"Avance."/"nova aba" sozinhos (sem "no navegador") não
       eram reconhecidos — forma exata usada no exemplo browser da missão.
    7. Novo: `files_open_named` — abrir um arquivo específico por nome; só
       existia abrir o último baixado.
  build ativo depois desta rodada: `release-candidate-openfile-20260905-2323`
    (8 commits, todos com teste de regressão + validação incremental sem
    falha nova em relação ao baseline).
  ainda por testar/mapear: disco/bateria via LLM+tool (mesmo caminho que RAM,
    provado funcionar, não testado isoladamente por flakiness do
    computer-use ao digitar — não é suspeita de bug real), localizar arquivo
    sem pasta explícita (hoje exige pasta por design de segurança —
    provavelmente intencional, não gap), sinônimos de fala não cobertos
    (ex.: "silencie o som" vs "silencia" já suportado) — não perseguir
    infinitos sinônimos, só os que aparecerem em uso real.

## TODO (Missão Jarvis, ordem de dependência — ver CURRENT_MISSION.md)

- ID: T-JARVIS-QUALIDADE-RAM
  owner: a definir
  scope: resposta de "Quanto de RAM estou usando?" vem com um preâmbulo
    irrelevante sobre "créditos de API" antes do dado real. Não bloqueia o
    golden path (a métrica real está correta), mas é ruído de prompt a
    limpar.
  files: provavelmente prompt/contexto do orchestrator/model router
  DoD: resposta cita só o que foi perguntado

- ID: T-BACKLOG-F1.1 (preservado, não descartado)
  owner: Voice Lead → `voice-lead` (time novo)
  scope: voz Kore funcionando na saída — retomada quando a missão chegar na
    camada Voice (prioridade 3 da Missão Jarvis), reaproveitando o trabalho já
    feito
  files: `core/gemini_live_voice.py`, `core/voice_tts.py`, `core/ipc_handlers.py` (_speak_response, trava)
  DoD: teste físico — Alex ouve a voz Kore, sem fallback silencioso pra SAPI

- ID: T-BACKLOG-F1.2 (preservado)
  owner: a definir
  scope: latência mínima de resposta — entra junto com a integração de Voice
  files: `core/model_router.py`
  DoD: número em ms, antes/depois, medido por `[VOICE_TRACE]` + SQLite

- ID: T-BACKLOG-F1.3 (preservado)
  owner: Voice Lead → `voice-lead` (time novo)
  scope: microfone sem loop com a própria voz da ZARA — entra junto com Voice
  files: `frontend/src/renderer/lib/aecAudio.ts`, `core/windows_audio.py`
  DoD: teste físico — ZARA não se ouve, barge-in corta áudio de verdade

- ID: T-JARVIS-P1-APPS
  owner: a definir
  scope: Native App Host prototype — 1 app desktop real (não web wrapper)
  files: a mapear
  DoD: app desktop real controlado pela ZARA, limitação documentada se não
    for possível reparenting estável

- ID: T-JARVIS-P1-MEMORY
  owner: Memory/Intelligence Lead (time novo — a criar)
  scope: conectar tela Memória à memória real (`memory/memory_manager.py`,
    `core/obsidian_bridge.py`) — sem grafo fake, sem segunda memória
  files: `memory/*`, `core/obsidian_bridge.py`, tela Memória do frontend
  DoD: escrever memória real, reiniciar, recuperar

## Evidence addendum — 2026-09-23 packaged voice and NVIDIA TTS

- Exact F1 candidate passed one synthetic PT-BR Gemini Live exchange in packaged runtime: correct transcript and text reply, 16 PCM audio blocks delivered to renderer. Measured 4.167 s from estimated synthetic speech end to first output block; one observation, not a median or physical approval.
- Buffer underrun metrics were not captured. A second attempt timed out before microphone capture; its sidecar log has no voice-start marker. Cause unknown.
- NVIDIA Magpie multilingual returned 86 voice names, including three pt-BR voices; one 3.11 s WAV was synthesized. This is catalog exploration only; no app integration.
- User system audio restored to the measured original 98%, unmuted. Generated isolated app profiles, including copied provider config, moved to `_quarentena/organizacao-2026-09-23/voz-testes-runtime/` with manifest; credential values were not logged.
- P1.6/P1.7 remain open. F2 remains blocked until Alex’s physical voice approval.

## Evidence addendum — voice-to-PC runtime (2026-09-23)

- Exact packaged candidate recognized synthetic PT-BR voice command “diminua o volume”; app dispatched `os_volume`, Windows readback changed 30%→20%, reply text matched, and the packaged action restored the test level to 30%. Independent final Windows readback: 98%, unmuted.
- Kore output reached the renderer (6 blocks, 49,920 bytes; about 1.04 s PCM). First block was 1.952 s after estimated synthetic speech end. Do **not** mark the spoken reply complete: trace includes `BARGE_IN` and `TTS_ABORT` before `voice-stop`; UI leaving “speaking” conflicted with backend trace. P1.4/P1.5 remain open.
- Evidence: `.unlazy/zara-master-20260923/voice-test/packaged-gemini-voice-volume-complete-report.json` and `...complete-traces.txt`. The EXE remains `release-candidate-f1-voz-20260923-114336`; physical Alex approval still required.

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

**Ainda aberto:** voz Kore limpa no ouvido do Alex, buffer sem falha em fala real e fallback sem troca no meio da frase (`P1.4/P1.5`); comparação física antes/depois (`P1.6`) e aprovação do Alex (`P1.7`); inventário restante de F0, demais famílias de PC e todas as fases F2–F4. A interrupção interna do Gemini passou no candidato empacotado acima; isso ainda não substitui o teste físico.

### Janela atual para teste do Alex — 2026-09-23

- Build ativo e janela visível: `release-candidate-f1-voice-interrupt-20260923-1756`, BUILD_ID e hashes em `ZARA_ACTIVE_BUILD.json`; janela `ZARA 3.0 — Neural Interface`, processo principal 15944, sidecar iniciado e handshake `SYS: Interface neural pronta` registrado. IPC `audio_status` e `engine-list` responderam no mesmo candidato antes de reabrir sem porta remota de depuração.
- A janela aberta usa perfil isolado preservado em `_quarentena/organizacao-2026-09-23/active-candidate-open/final-20260923-181539-g62t32ed/`, com Lab/autopilot em OFF. O app anterior continua oculto na bandeja com o perfil de produção, sem ter sido encerrado.
- A lista no perfil isolado devolve 12 modelos como `DISCOVERED_UNPROVEN` e fallback 9Router `AUTH_REQUIRED`. Não afirmar que os modelos estão disponíveis; F2 continua sem implementação/prova. GEMINI_API_KEY está disponível ao processo de teste, sem ser copiada ao perfil.
- Relatório de abertura/IPC: `.unlazy/zara-master-20260923/voice-test/server-interrupt-ownership/final-open-report-20260923-181539.json`. Porta de depuração foi removida da janela final.

### Evidência adicional — entrada de texto e voz no EXE F1 (2026-09-23)
- `PACKAGED_RUNTIME`: pelo caminho normal de conversa, ZARA abriu Notepad, digitou `ZARA_TEST_20260923_DIGITACAO`, a UI Automation do Windows leu o conteúdo, `Desfaça` deixou o campo vazio e ZARA fechou o processo de teste. Estados verificados fora da resposta textual; clipboard original preservado. Perfil isolado em `_quarentena/organizacao-2026-09-23/voz-testes-runtime/controle-notepad-digitacao-20260923/` com manifest.
- Tempos após o backend ficar pronto: abrir 1.977 ms, digitar 335 ms, desfazer 218 ms, fechar 153 ms. Backend frio do perfil isolado: 15.813 ms; uma amostra, não mediana.
- Resultado v2 atualizado acima: a primeira tentativa expirou antes da captura; Gemini handshake NÃO CONFIRMADO. A repetição captou sinal digital contínuo, mas não prova fala audível/inteligível. Volume foi restaurado a 98%, sem mudo. Relatório v2 preservado.


## Read-only audits — F2 models and F3 Lab (2026-09-23)

- F2 SOURCE audit only: the home selector reads FrontBrain's hard-coded brains plus OpenCode descriptors; FrontBrain caps OpenCode at eight and filters NVIDIA. The provider registry has NVIDIA, but model discovery is not invoked on this path. Kimi K3 is absent from the inspected active catalog; no account call checked whether Alex's NVIDIA endpoint returns it or whether it is free. Gemini Live uses a separate real-time voice transport and voice-status IPC, not the text-brain selector. Adding it as a text brain would conflate two APIs. No code, credentials, or NVIDIA endpoint changed/queried. Main paths: frontend/src/renderer/components/zara-home/BrainSelector.tsx; core/lab_v1/front_brain.py; core/lab_v1/providers/nvidia.py; core/lab_v1/service.py; core/ipc_handlers.py.
- F3 SOURCE/UI audit only: app startup creates LabV1Service and starts the supervisor when background_enabled is true; this is bounded observation/work, not a free conversation loop. Room mission entry needs an action verb plus target. Safe patch → tests → independent review → candidate/rollback structures exist in source, but no end-to-end packaged mission has been demonstrated; the production approval/promotion callback is not proven connected. Quota pause has persisted support; a resume action was not found in preload/UI.
- PACKAGED_RUNTIME observation after opening the official EXE: Lab DB counts remained 2 QUEUED, 1 RUNNING, 0 mission_controls; policy enabled/background_enabled=true, paid_allowed=false, next evolution check tomorrow local. No autonomous coding mission or bot conversation started. No message bodies were read.
- Therefore F2 model selection and F3 autonomous coding remain NOT DONE. Minimum F3 runtime proof is one bounded code request through the packaged Lab; inspect plan/runs/diff only inside sandbox, require independent review and passing candidate validation, then close/reopen and confirm mission persistence. Stop at VERIFIED_AWAITING_APPROVAL; do not auto-promote.


## ZARA-PC-NAMED-WINDOW-NOTEPAD-20260923

- status: PACKAGED_RUNTIME_PASS; ALEX_VOICE_PHYSICAL_PENDING
- Source patch: parser now maps minimize/maximize/restore phrases for Bloco de Notas/Notepad to the existing allowlisted window executor. Executor matches the Notepad process or title. No ipc_handlers edit.
- Regression: 48 tests in tests/test_window_control.py passed. Before the source patch, the five added regressions failed for the missing parser/matcher/action allowance.
- Packaged proof on release-candidate-f1-notepad-control-20260923-1703: normal conversation route returned engine=pc_control; independent Win32 readback verified maximize, restore, minimize, restore; close ended only the newly created blank Notepad process. Report: .unlazy/zara-master-20260923/pc-controls/notepad-named-target/packaged-smoke-report.json.
- Individual request timings after backend readiness: 226.5 ms maximize, 292.6 ms restore, 177.8 ms minimize, 205.3 ms restore. Cold backend readiness was 18.618 s; these are not voice-response latency measurements.
- Candidate identity: EXE SHA256 67DC2A7036860A68E5312C212C31B8772AC463ED0289FCC44897867F55075E89; backend SHA256 696BEF30954613E5AD9BAAFAD7FFC5D9ECF8DA9FB5ADC5A7791EECE83691994D; ASAR SHA256 2E2DA47E5D6F2781AC86F24227B98B14EEC214BCCF26BF406AF49811C5B5623C. EXE/ASAR hashes match the base because this candidate is a sidecar swap; backend hash differs.
- App open: PID 1264, title ZARA 3.0 — Neural Interface, responding. P1.7 voice physical approval remains pending; this test used synthetic text input to the packaged conversation route, not Alex’s voice.
- No phase commit was made: F1 is still incomplete, the branch has unrelated dirty work, and this bounded fix does not close the phase.
