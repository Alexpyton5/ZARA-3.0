# ZARA — Missão Atual

Atualizar conforme o trabalho progride. Não é histórico — é só o estado agora.

## Objetivo atual — OPENCODE + VOZ + LAB 24H (2026-09-22, autopilot do Alex até 20:00)

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
