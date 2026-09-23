# ZARA — Missão Atual

Atualizar conforme o trabalho progride. Não é histórico — é só o estado agora.

## Objetivo atual — Plano mestre F0–F4 aprovado por Alex (2026-09-23)

Concluir na ordem do plano enviado por Alex. Cada fase tem build e commit próprios; build apenas por `tools/build_candidate.py`; atualizar `ZARA_ACTIVE_BUILD.json`; preservar material incerto em `_quarentena/` com manifest. Voz só é aprovada fisicamente por Alex.

### Estado

- **F0 — EM FECHAMENTO.** P0.2 concluído. P0.3 passou no app empacotado com leitura independente do Windows: volume 98→88→98, mudo ativado/desativado e brilho 0→5→0; estado original restaurado. Identidade do EXE/backend/ASAR verificada; `TestBuildIdentity` 2/2 passou.
- **P0.1 — PARCIAL.** Manifesto SHA-256 registra os 819 arquivos já presentes em `_quarentena/` (57.749.157 bytes). Nada foi apagado nem classificado como descartável. A lista das “35 stubs/memórias mortas” não existe de forma reconciliada; itens incertos continuam protegidos. Nenhum espaço foi liberado.
- **F1 — A SEGUIR.** Voz fluida e controles de PC, conforme P1.1–P1.8. Aprovação física de fala/latência segue pendente de Alex.
- **F2–F4 — NÃO INICIADAS.** Manter a ordem definida no plano mestre; preservar o backlog WOW existente.

### Build empacotado F0

- BUILD_ID: `release-candidate-f0-wt-20260923-190251-20260923-1904`
- EXE: `frontend/release-candidate-f0-wt-20260923-190251-20260923-1904/win-unpacked/ZARA 3.0.exe`
- SHA-256 e recibo completo: `ZARA_ACTIVE_BUILD.json` e `frontend/.../BUILD_INFO.json`.
- Prova de identidade: `.unlazy/f0-current-worktree/candidate-identity-report.json`.
- Prova de controle empacotado: `_quarentena/organizacao-2026-09-23/pc-controls-probes/20260923-190841-2868/REPORT.json`.

O candidato foi encerrado após o teste isolado; o build final da missão deve ser aberto para Alex quando as fases implementáveis terminarem.

### Ordem oficial

F0 Higiene → F1 Voz fluida → F2 Modelos grátis → F3 Zara Lab (P3.3, P3.4, P3.1, P3.2, P3.5, P3.7, P3.6) → F4 Refino técnico. A lista detalhada permanece na solicitação do proprietário e no registro `T-ZARA-MASTER-20260923` em `TASK_BOARD.md`.

## Próxima ação

Fechar o registro e commit próprios de F0; em seguida trabalhar em F1 sem promover prova automatizada a aprovação física.

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
