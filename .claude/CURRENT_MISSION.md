# ZARA — Missão Atual

Atualizar conforme o trabalho progride. Não é histórico — é só o estado agora.

## Objetivo atual — Plano mestre F0–F4 aprovado por Alex (2026-09-23)

Concluir na ordem do plano enviado por Alex. Cada fase tem build e commit próprios; build apenas por `tools/build_candidate.py`; atualizar `ZARA_ACTIVE_BUILD.json`; preservar material incerto em `_quarentena/` com manifest. Voz só é aprovada fisicamente por Alex.

### Contrato ativo — LAB-VISIBLE-RUNTIME-20260925

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
- **Build ativo do Lab:** `release-candidate-lab-continuous-autonomy-20260925-20260925-112133`; backend SHA-256 `FB07B6E5C25A3C17040444B24F4AB41BCB59A6B4C6091BDF30223AC7C02052A6`. Há exatamente **1 build operacional em `frontend/` e 1 janela principal da ZARA**. Os 25 builds anteriores foram movidos sem exclusão para `_quarentena/builds-single-active-20260925-112656/`, com `MANIFEST.json` de rollback/auditoria. O supervisor migrou do limite legado de 1 missão/dia para ciclo de 5 minutos com teto finito de 288/dia. Isso não fecha os gates físicos de voz nem reclassifica F0/F1/F2/F4.

- **F0 — PARCIAL.** P0.2 concluído. P0.3 passou no app empacotado com leitura independente do Windows: volume, mudo e brilho foram alterados e restaurados. P0.1 segue parcial: não houve exclusão nem espaço liberado. F1 já tem implementação e candidato devido ao trabalho anterior, mas a higiene ainda não pode ser chamada de concluída.
- **P0.1 — PARCIAL.** Manifesto do worktree atualizado para 1.033 arquivos preservados (93.428.117 bytes), com manifestos anteriores guardados em pre-refresh e pre-refresh-2. Leitura somente do checkout principal encontrou 26,2 GB já em `_quarentena/` (164.642 arquivos), incluindo fontes de legacy; nada foi movido/apagado. A lista das “35 stubs/memórias mortas” e a meta de 8,5 GB seguro para remoção não foram comprovadas; nenhum espaço foi liberado.
- **F1 — EM EXECUÇÃO, GATES PARCIAIS.** Candidato empacotado exato release-candidate-f1-voice-20260923-195354. Testes focados: 118 passaram, 22 foram pulados pelo limite conhecido do módulo de janela de voz. Runtime empacotado provou resposta direta Gemini Live→Kore em estímulo sintético (5.076 ms após última amostra falada) e controles por texto de volume/mudo/brilho, confirmados pelo Windows e restaurados. Um comando sintético por áudio pediu 80%, foi transcrito como 40% e alterou o volume para 40%; o estado foi restaurado para 98%. F0 não emitiu áudio para o mesmo estímulo; portanto não existe delta numérico antes/depois. Interrupção automatizada parcial; fallback TTS controlado e validação física continuam pendentes. Aprovação física de fala é exclusiva de Alex.
- **F2–F4 — NÃO INICIADAS.** Manter a ordem definida no plano mestre; preservar o backlog WOW existente.

### Build empacotado ativo F1

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

O candidato F1 exato já está aberto, com perfil normal, sem flags de microfone falso; janela e EXE foram confirmados. Alex precisa validar fala e interrupção quando voltar. Fallback empacotado e comparação numérica de latência permanecem sem prova; só então abrir F2.

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
