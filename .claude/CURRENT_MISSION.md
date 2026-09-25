# ZARA — Missão Atual

Atualizar conforme o trabalho progride. Não é histórico — é só o estado agora.

## Objetivo atual — Plano mestre F0–F4 aprovado por Alex (2026-09-23)

Concluir na ordem do plano enviado por Alex. Cada fase tem build e commit próprios; build apenas por `tools/build_candidate.py`; atualizar `ZARA_ACTIVE_BUILD.json`; preservar material incerto em `_quarentena/` com manifest. Voz só é aprovada fisicamente por Alex.

**Foco operacional atual:** por instrução de Alex, priorizar a autonomia real do Zara Lab e manter voz pausada. Isso não conclui nem apaga os gates F0/F1/F2/F4 do plano original.

**Marco ativo — M030:** conectar a memória compartilhada dos agentes ao vault Obsidian configurado. A inspeção confirmou apenas metadata: configuração existe, vault acessível e pasta `Zara-Memoria` contém nota(s). M030 adicionou a injeção limitada de memória; o uso em chamada real e a proveniência visível ainda não foram provados no app empacotado. Limite desta fatia: consultar somente `Zara-Memoria`, nunca percorrer notas pessoais; registrar caminhos relativos e horário; provar a consulta numa missão read-only visível no app empacotado. O código M030 foi integrado e o build candidato abriu; a prova da chamada real continua pendente porque uma missão anterior mantém a sala bloqueada. O resíduo operacional M000 (registro de lease/política) segue preservado e fora da mutação M030.

### Prioridade explícita de Alex — ZARA-LAB-LIVING-TEAM-20260925

Alex determinou que o Lab vire uma única sala contínua onde um CEO convoca especialistas, leitores inspecionam a ZARA, pesquisadores buscam melhorias com fontes, todos consultam memória compartilhada do vault Obsidian, e engenheiros implementam mudanças reais com validação/revisão/build. O Codex implementa diretamente no source enquanto o Lab não consegue concluir a própria missão. Plano completo e prompt operacional: `.claude/ZARA_LAB_LIVING_TEAM_MISSION.md`; gates: `.unlazy/zara-lab-living-team-20260925/GATES.md`.

**Estado inicial:** 35 sessões e 182 mensagens no DB canônico; mensagens ainda ligadas a sessões e sem feed unificado; print mostra missões separadas e uma candidata de código aguardando revisão; Obsidian compartilhado pelo Lab não está comprovado. Primeiro marco de produto: M010 — feed persistente ZARA Core. Preservar os 101 caminhos dirty/untracked anteriores. Não iniciar outra missão paralela nem abrir outro app.

**Progresso desta execução (2026-09-25):** M010 e M020 foram gerados por `tools/build_candidate.py` e observados no app empacotado. A tela mostra uma só entrada `ZARA Core`, 34 missões no histórico e mensagens de missões distintas com separadores. M020 agora abre o app diretamente na sala; após reiniciar, as contagens canônicas permaneceram em 35 sessões, 197 mensagens e 120 tarefas, estáveis em duas leituras. Capturas: `.unlazy/zara-lab-living-team-20260925/PACKAGED_RUNTIME_M010_20260925.png` e `PACKAGED_RUNTIME_M020_20260925.png`. Build ativo: `release-candidate-lab-resume-room-20260925-151800`; hashes de EXE/ASAR/backend conferidos; uma janela principal aberta e release anterior preservada para rollback. M000 segue parcial até conciliar lease e política do supervisor.

**Progresso M030 (2026-09-25):** a correção que libera o Lab após trabalho pausado foi empacotada; a missão real entrou na sala canônica. Essa prova encontrou um `NameError` no carimbo de data da memória, antes de qualquer chamada ao modelo. Correção e regressão específica estão no source; os testes focados passaram. Próximo: novo build oficial, retomar a prova read-only no app real e confirmar a fonte no feed sem mexer na tentativa bloqueada nem na missão histórica.

### Entrega documental concluída — ZARA-LAB-MASTER-MANUAL-20260925

- Manual: `.claude/ZARA_LAB_AUTOPILOT_MASTER_MANUAL.md`.
- Inclui estado atual medido, correções ao relatório Hermes, sequência M000–M170, critérios de pronto, arquivos permitidos, evidência visível e rollback.
- Esta entrega alterou somente documentação. Nenhum fonte de produto, banco, vault ou build foi alterado.
- Próxima missão de produto ainda não iniciada: **M000 — Verdade operacional e uma única ZARA**.

### Contrato concluído — LAB-VISIBLE-RUNTIME-20260925

- **GOAL:** toda missão real de desenvolvimento/autonomia deve nascer no ZARA Lab canônico e ficar fiscalizável na UI real.
- **SCOPE:** regra permanente de operação + launcher oficial de missão visível usando o mesmo `LabStore` canônico exibido pelo app.
- **FILES_ALLOWED:** `.claude/DECISIONS.md`, `.claude/WORKING_MODEL.md`, `.claude/CURRENT_MISSION.md`, `tools/zara_lab_visible_mission.py`, `core/lab_v1/mission_controller.py`, `core/lab_v1/source_mission.py`, `core/lab_v1/autopilot.py`, `core/lab_v1/supervisor.py`, `core/lab_v1/workforce_policy.py`, `tests/test_lab_source_mission.py`, `tests/test_lab_autopilot.py`, `tests/test_lab_supervisor.py`, `ZARA_ACTIVE_BUILD.json`, `ZARA_ACTIVE_BUILD.txt` e os artefatos gerados por `tools/build_candidate.py` para o novo candidato.
- **FILES_FORBIDDEN:** fonte do produto fora desse escopo, builds existentes, `_quarentena/`, dados/memórias do usuário.
- **BASELINE:** `38fbe9a`; worktree já estava dirty antes desta tarefa.
- **EXPECTED_DELTA:** harness/perfil isolado deixa de valer como prova de missão real; launcher exige o app canônico aberto e grava a missão no banco real que o Lab mostra; inspeção que propõe nenhuma mudança recebe segunda revisão independente antes de encerrar; JSON de planejamento fica como artefato de máquina e a conversa mostra linguagem natural; etapas reais de teste aparecem como atualização factual na conversa; o supervisor deixa o limite legado de 1 missão/dia e entra no ciclo contínuo autorizado pelo Alex, mantendo orçamento diário finito.
- **VALIDATION:** iniciar missão curta pelo launcher, verificar a mesma `session_id` no snapshot canônico e manter a execução visível no Lab.
- **PACKAGED_TEST:** reconstruir somente o sidecar por `tools/build_candidate.py`, conferir identidade/hash do EXE e backend, abrir apenas o novo build ativo e confirmar que uma missão canônica continua visível no Lab real.
- **PHYSICAL_TEST:** Alex consegue abrir a conversa no Lab e fiscalizar mensagens, tarefas, runs e entregas dessa mesma sessão.
- **ROLLBACK:** remover o launcher e reverter apenas os blocos desta decisão/regra.
- **STOP_CONDITION:** não declarar missão real comprovada se ela só existir em `.unlazy`, `tmp`, `ZARA3_HOME` alternativo ou harness isolado.

### Estado

**Mudança de prioridade do Alex (2026-09-23):** pausar trabalho de voz e focar Zara Lab em iniciativa, conversa entre agentes e código autônomo em sandbox. F1 continua pendente; nenhuma fase é reclassificada como concluída.

**Correção de evidência por decisão do Alex (2026-09-25):** qualquer execução anterior que tenha usado `ZARA3_HOME` descartável, `.unlazy/`, `tmp` ou harness isolado deixa de contar como prova de missão/autonomia real do Lab. Esses resultados passam a valer apenas como evidência técnica auxiliar. A aceitação daqui para frente exige uma sessão no banco canônico do Lab, visível na UI enquanto os agentes trabalham.

- **ZARA LAB AUTONOMY — PACKAGED_RUNTIME CONCLUÍDO (2026-09-25).** No build empacotado, sem mensagem do Alex, o Lab abriu a missão `session_5ae1423b4098`, planejou em linguagem natural, recuperou automaticamente de indisponibilidade de recurso por fallback autorizado, criou patch isolado, passou 16/16 testes focados, recebeu revisão independente PASS, construiu o candidato `release-candidate-lab-source-20260925-051603`, passou canário e promoveu automaticamente a mudança LOW-risk. O journal `artifacts/releases/source-20260925-051655-271259/SOURCE_PROMOTION.json` terminou `COMMITTED`. Testes transacionais de promoção/rollback: 4/4 PASS. Evidência: `.unlazy/zara-lab-autonomy-20260923/AUTONOMY_E2E_EVIDENCE_20260925.md`.
- **Build ativo apontado pelo JSON na auditoria de 2026-09-25:** `release-candidate-lab-source-20260925-120718`; backend SHA-256 `79943875F0F2942ACDC28412112566E63E311EF6819328A433FC02101DAFEE48`. Foi observada também a pasta `release-candidate-lab-continuous-autonomy-20260925-20260925-112133` em `frontend/`, logo existem duas pastas de release e a documentação anterior estava desatualizada. M000 deve confirmar o processo em execução e preservar qualquer build excedente em `_quarentena/` com manifesto. Os 25 builds anteriores já registrados na quarentena não foram apagados. O supervisor/scheduler e o limite diário continuam governados pela política persistida. Isso não fecha os gates físicos de voz nem reclassifica F0/F1/F2/F4.

- **F0 — PARCIAL.** P0.2 concluído. P0.3 passou no app empacotado com leitura independente do Windows: volume, mudo e brilho foram alterados e restaurados. P0.1 segue parcial: não houve exclusão nem espaço liberado. F1 já tem implementação e candidato devido ao trabalho anterior, mas a higiene ainda não pode ser chamada de concluída.
- **P0.1 — PARCIAL.** Manifesto do worktree atualizado para 1.033 arquivos preservados (93.428.117 bytes), com manifestos anteriores guardados em pre-refresh e pre-refresh-2. Leitura somente do checkout principal encontrou 26,2 GB já em `_quarentena/` (164.642 arquivos), incluindo fontes de legacy; nada foi movido/apagado. A lista das “35 stubs/memórias mortas” e a meta de 8,5 GB seguro para remoção não foram comprovadas; nenhum espaço foi liberado.
- **F1 — EM EXECUÇÃO, GATES PARCIAIS.** Candidato empacotado exato release-candidate-f1-voice-20260923-195354. Testes focados: 118 passaram, 22 foram pulados pelo limite conhecido do módulo de janela de voz. Runtime empacotado provou resposta direta Gemini Live→Kore em estímulo sintético (5.076 ms após última amostra falada) e controles por texto de volume/mudo/brilho, confirmados pelo Windows e restaurados. Um comando sintético por áudio pediu 80%, foi transcrito como 40% e alterou o volume para 40%; o estado foi restaurado para 98%. F0 não emitiu áudio para o mesmo estímulo; portanto não existe delta numérico antes/depois. Interrupção automatizada parcial; fallback TTS controlado e validação física continuam pendentes. Aprovação física de fala é exclusiva de Alex.
- **F2–F4 — NÃO INICIADAS.** Manter a ordem definida no plano mestre; preservar o backlog WOW existente.

### Candidato F1 histórico — não é o build ativo do Lab

- BUILD_ID: `release-candidate-f1-voice-20260923-195354`
- EXE: `frontend/release-candidate-f1-voice-20260923-195354/win-unpacked/ZARA 3.0.exe`
- EXE SHA-256: `67DC2A7036860A68E5312C212C31B8772AC463ED0289FCC44897867F55075E89`
- Backend SHA-256: `A96451320C554D88765F32F076A9D418133285FBB783926E2E1333A48AC9F3D6`
- ASAR SHA-256: `2F8A6521C5A9F3FDCC05CF2D1144329D22FB31D824C58709D6FA6DD7A233FAE8`
- Identidade e runtime: `.unlazy/f1-voice/candidate-identity-report.json` e `.unlazy/f1-voice/PACKAGED_RUNTIME_REPORT.md`.

### Build empacotado F0 (baseline)

- BUILD_ID: `release-candidate-f0-wt-20260923-190251-20260923-1904`
- EXE: `frontend/release-candidate-f0-wt-20260923-190251-20260923-1904/win-unpacked/ZARA 3.0.exe`
- SHA-256 e recibo completo: `ZARA_ACTIVE_BUILD.json` e `frontend/.../BUILD_INFO.json`.
- Prova de identidade: `.unlazy/f0-current-worktree/candidate-identity-report.json`.
- Prova de controle empacotado: `_quarentena/organizacao-2026-09-23/pc-controls-probes/20260923-190841-2868/REPORT.json`.

O candidato foi encerrado após o teste isolado; o build final da missão deve ser aberto para Alex quando as fases implementáveis terminarem.

### Ordem oficial

F0 Higiene → F1 Voz fluida → F2 Modelos grátis → F3 Zara Lab (P3.3, P3.4, P3.1, P3.2, P3.5, P3.7, P3.6) → F4 Refino técnico. A lista detalhada permanece na solicitação do proprietário e no registro `T-ZARA-MASTER-20260923` em `TASK_BOARD.md`.

## Próxima ação

**M000 em andamento.** O app foi reaberto uma única vez pelo EXE de `ZARA_ACTIVE_BUILD.json` (`release-candidate-lab-source-20260925-120718`); a janela principal e os processos filhos apontam para essa mesma pasta. JSON, EXE e backend SHA conferem. Há uma release anterior, mas ela é referenciada como `BASE_BUILD` e rollback em `SOURCE_PROMOTION.json`; fica protegida e não será movida como lixo.

Uma sessão anterior de inspeção (`session_8819d4e41e01`) ficou `BLOCKED` por `INSPECTION_REVIEW_SCHEMA`; não tinha patch nem alterações no produto. Foi encerrada pelo serviço real do Lab como `CANCELLED`, mantendo histórico e artefatos. Isso liberou a fila sem apagar a conversa.

O Lab real inicia em `Hoje` a cada abertura (`ZaraHome` define `activeNav='Hoje'`), e uma missão em estado `BLOCKED` impedia `Autopilot.start` de aceitar outra. Esses são defeitos de continuidade/roteamento a tratar nas missões correspondentes do manual; não os contornar com sessões paralelas. O controle visual deste runtime falhou, então a rota do Lab não foi confirmada pela tela; Alex pode selecionar “ZARA Lab” para acompanhar a sessão canônica.

Próximo passo: criar e concluir a sessão visível **M000** usando `tools/zara_lab_visible_mission.py`, conferir o mesmo `session_id` no DB canônico e na tela, e só então abrir **M010**. Não executar pytest nem outro harness. F1 continua pausada por decisão de Alex.

## Histórico anterior — OPENCODE + VOZ + LAB 24H (2026-09-22)

O estado e as evidências anteriores foram preservados no histórico desta missão e nos relatórios `.unlazy/zara-master-20260923/`. Não apagar ou reclassificar itens do backlog.

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

T-ZARA-MASTER-20260923 — foco atual Zara Lab. Entrega documental ZARA-LAB-MASTER-MANUAL-20260925 concluída; preparar M000 — ver `TASK_BOARD.md` e `.claude/ZARA_LAB_AUTOPILOT_MASTER_MANUAL.md`.

## Owner da task

Chief of Staff (sessão principal), delegando por área conforme necessário.

## Files

Para a próxima missão M000: `ZARA_ACTIVE_BUILD.json`, `ZARA_ACTIVE_BUILD.txt`,
`.claude/CURRENT_MISSION.md`, `.claude/TASK_BOARD.md`,
`.claude/rules/build-release.md`, `.claude/rules/test-run-policy.md`,
`tools/build_candidate.py` e o manifesto exato de quarentena declarado antes
de mover qualquer build.

## Dependencies

Nenhuma pendência externa conhecida no momento da abertura desta missão.

## Status

`READY — M000 ainda não começou`.

## Next action

Começar M000 no build apontado por `ZARA_ACTIVE_BUILD.json`, confirmar uma só
ZARA/build operacional e atualizar o estado oficial. Depois seguir M010 em
diante na ordem do manual, sem marcar voz ou fases antigas como concluídas.
