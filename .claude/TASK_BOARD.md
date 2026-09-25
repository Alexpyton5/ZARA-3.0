# ZARA — Task Board

Formato simples. Não virar burocracia.

## COMPLETED DOCUMENT TASK

- ID: ZARA-LAB-MASTER-MANUAL-20260925
  goal: produzir um manual factual e sequencial para transformar o Zara Lab em um laboratório autônomo, persistente, visível e seguro, reutilizando os componentes que já existem e separando fatos de hipóteses.
  scope: auditoria de estado já registrada + spot-checks read-only dos pontos de maior risco + síntese do relatório Hermes + missões pequenas com dependências, arquivos permitidos, validação real e rollback.
  files_allowed: `.claude/TASK_BOARD.md`, `.claude/CURRENT_MISSION.md`, `.claude/ZARA_LAB_AUTOPILOT_MASTER_MANUAL.md`.
  files_forbidden: source do produto, testes, banco do Lab, memória/vault do usuário, build identity, diretórios de release, `_quarentena/`, `.unlazy/` e quaisquer outros artefatos operacionais existentes.
  baseline: HEAD `25d6be0`, branch `codex/zara-master-20260923`, 99 paths dirty/untracked já presentes; preservar sem reset, limpeza, movimentação ou inclusão acidental no commit documental.
  expected_delta: manual em português com estado medido, divergências do relatório Hermes, arquitetura-alvo, missões implementáveis em sequência, evidência mínima, gates de segurança/continuidade e fechamento por fase com build único, commit e push.
  validation: revisão estrutural do documento e do diff limitado aos três arquivos permitidos; não executar a suíte nem declarar prova de runtime nova para uma tarefa documental.
  packaged_test: N/A para documentação; usar a identidade atual do app somente como dado do estado auditado.
  physical_test: N/A para documentação; todo gate de produto descrito no manual exige missão visível no Lab canônico empacotado.
  rollback: reverter somente as alterações documentais desta tarefa; não restaurar ou descartar os 99 paths preexistentes.
  stop_condition: se uma afirmação do material Hermes não corresponder ao checkout ou à evidência disponível, registrá-la como não confirmada e transformar sua verificação em gate da primeira missão aplicável.
  status: COMPLETE — manual criado em `.claude/ZARA_LAB_AUTOPILOT_MASTER_MANUAL.md`; documentação reconciliada; nenhuma suíte, fonte, banco, vault ou build foi alterado nesta tarefa.

## MASTER MISSION IN PROGRESS

- ID: T-ZARA-MASTER-20260923
  owner: Chief of Staff (sessão principal)
  scope: concluir o plano F0–F4 de Alex, na ordem aprovada, com build e commit separados por fase, identidade do build ativo e evidência por runtime real.
  override de prioridade: em 2026-09-23 Alex pediu pausar voz e priorizar Zara Lab autônomo. F0–F2 e F1 físico continuam pendentes; backlog preservado.
  estado Lab autonomy (2026-09-25): PACKAGED_RUNTIME registrado para a fatia `ZARA-LAB-AUTONOMY-20260923`. A sessão `session_5ae1423b4098` executou planejamento visível → patch isolado → testes focados → reviewer → build → canário → promoção automática LOW-risk. A promoção foi registrada em `COMMITTED`; 4/4 cenários transacionais de promoção/rollback passaram. O build produzido naquela missão era `release-candidate-lab-source-20260925-051603`; não é o build atual. Evidência: `.unlazy/zara-lab-autonomy-20260923/AUTONOMY_E2E_EVIDENCE_20260925.md` — evidência complementar que precisa ser correlacionada com a sessão e UI canônicas para provar trabalho visível.
  identidade observada na retomada de 2026-09-25: ZARA_ACTIVE_BUILD.json aponta para `release-candidate-lab-source-20260925-120718`, backend SHA-256 `79943875F0F2942ACDC28412112566E63E311EF6819328A433FC02101DAFEE48`; foram encontradas duas pastas de release em `frontend/`, incluindo a antiga `release-candidate-lab-continuous-autonomy-20260925-20260925-112133`. Próxima: M000 reconcilia JSON, processo, documentação e pasta única, preservando excedentes em quarentena com manifesto.
  files: por fase, sob contrato TASK_ID; `core/ipc_handlers.py` continua sob trava do Chief.
  critérios: build apenas por `tools/build_candidate.py`; quarentena com manifest e sem apagar; testes automáticos direcionados; ações de PC aprovadas só por postcondição do Windows; voz aprovada fisicamente só por Alex; build final aberto e identificado.
  estado F0: fechado, exceto P0.1 parcial; P0.2 concluído; P0.3 passou no candidato empacotado, com volume, mudo e brilho alterados, lidos no Windows e restaurados; teste de identidade 2/2 passou. Candidato baseline `release-candidate-f0-wt-20260923-190251-20260923-1904`.
  estado P0.1: PARCIAL — manifesto do worktree atualizado cobre 1.033 arquivos preservados (93.428.117 bytes); manifestos anteriores guardados em pre-refresh e pre-refresh-2. O checkout principal já tem 26,2 GB/164.642 arquivos em quarentena; a maioria não foi auditada item a item. A pasta `voice/` preservada ali é usada somente por um teste legacy, não pelo runtime atual. Nenhum arquivo foi movido/apagado e nenhum espaço foi liberado; os “35 stubs/memórias mortas” e 8,5 GB seguros continuam sem prova.
  evidências: `.unlazy/f0-current-worktree/GATES.md`, `.unlazy/f0-current-worktree/candidate-identity-report.json`, `_quarentena/MANIFEST_P0.1_20260923.json`, `_quarentena/organizacao-2026-09-23/pc-controls-probes/20260923-190841-2868/REPORT.json`.
  próxima ação atual: executar M000 do manual do Zara Lab antes de outra edição de produto. Voz continua pausada por decisão de Alex; manter os gates F1/F2 sem reclassificá-los como concluídos.

  estado F1: candidato release-candidate-f1-voice-20260923-195354 validado por SHA. Testes direcionados 118 passaram e 22 foram pulados pelo módulo de voz com janela/hang conhecido. PACKAGED_RUNTIME: resposta direta no Gemini Live/Kore com PCM sintético (uma medição 5.076 ms, sem delta comparável porque F0 não respondeu); controles por texto de volume, mudo e brilho confirmados por leitura independente e restaurados. Falha real no probe sintético de voz→PC: pediu 80%, Gemini transcreveu 40%, Windows mudou para 40%; estado restaurado a 98%. Interrupção parcial observada; sem prova física nem teste de falha controlada de TTS. Global frontend lint permanece com 5 erros e 62 avisos em arquivos fora da alteração F1.
  evidência: `.unlazy/f1-voice/TEST_REPORT.md`, `.unlazy/f1-voice/GATES.md`, `.unlazy/f1-voice/PACKAGED_RUNTIME_REPORT.md`, `.unlazy/f1-voice/candidate-identity-report.json`.

O ticket antigo T-JARVIS-P0-02 fica preservado como histórico de trabalho; a prioridade atual é a ordem F0–F4 de T-ZARA-MASTER-20260923.

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

## READY — CURRENT FOCUS

- ID: ZARA-LAB-M000
  owner: Chief of Staff
  scope: reconciliar build ativo, processo, diretórios de release, banco canônico e comando de smoke; preservar uma única ZARA operacional.
  status: READY — ainda não iniciado.
  files: conforme o cartão M000 em `.claude/ZARA_LAB_AUTOPILOT_MASTER_MANUAL.md`; declarar o caminho exato do manifesto antes de qualquer movimentação.
  acceptance: JSON/documentação/processo/única pasta ativa concordam; build excedente vai para `_quarentena/` com manifesto, sem exclusão; a mesma sessão do Lab fica visível no app.

## IN PROGRESS / PRESERVED BACKLOG

Foco atual de execução: Zara Lab, começando por ZARA-LAB-M000 acima. O ticket T-JARVIS-P0-02 abaixo fica preservado e pausado pela prioridade atual de Alex; não compete com as missões do Lab.

- ID: T-JARVIS-P0-02
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
