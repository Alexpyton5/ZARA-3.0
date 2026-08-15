# Regras para `core/` — sidecar Python

Aplica-se a: `core/**/*.py`, `memory/**/*.py`, `integrations/**/*.py`, `main.py`, `build_exe.py`

## Mapa mínimo antes de editar

- `core/ipc_handlers.py` — dispatcher central (classe `IPCHandler`, ~2700 linhas)
  - `handle_send_message` — entrada de **texto**
  - `_process_voice_message` — entrada de **voz**
  - `_on_speech_recognized` — STT local → `_process_voice_message`
  - `_on_gemini_live_turn` — Gemini Live → wake gate → `_process_voice_message`
  - `_speak_response` — saída TTS
  - `handle_interrupt` — barge-in via UI
- `core/pc_voice_intent.py` — `PcVoiceIntentDetector`, regex → nome de action
  - `_LOCAL_DETERMINISTIC_ACTIONS` — conjunto isento do gate do Supercérebro
  - `_blocked_by_superbrain(action)` — gate
- `core/action_registry.py` — registro/execução de actions
- `core/actions/*.py` — executores reais
- `core/voice_stt.py`, `core/voice_tts.py`, `core/gemini_live_voice.py` — camada de voz

## Invariante: voz e texto compartilham a cadeia

Ambas as entradas percorrem, **na mesma ordem**:

```
_try_jarvis_multi_action
_try_reminder_intent
_try_operational_memory_intent
_try_self_knowledge
_try_file_intent
_try_compound_pc_intent
_try_pc_intent
_looks_like_unhandled_local_action  (guard honesto)
LLM / orchestrator
```

**Qualquer PR que adicione um intent a um lado e não ao outro é regressão.**
Ao alterar a cadeia, alterar as duas funções e provar com a mesma frase nos dois caminhos.

## Invariante: reflexo local não depende do Supercérebro

Ação local determinística tem de estar em `_LOCAL_DETERMINISTIC_ACTIONS`, senão fica
bloqueada com Supercérebro OFF — que é o estado padrão de boot.

Ao adicionar uma action local nova, adicionar ao conjunto **e** cobrir com teste que rode
com `pc_control_allowed=False`.

## Invariante: resposta vem do executor

O texto de sucesso tem de ser derivado de `getattr(result, "output", ...)` ou de readback.
String fixa de sucesso sem checar `result.success` é falso sucesso e é proibida.

Resposta de modelo (LLM, Gemini Live) **nunca** é prova de ação. Em `_on_gemini_live_turn`
o rascunho remoto é descartado de propósito (`del model_text`). Não reintroduzir.

## Instrumentação

Manter e usar os marcadores:

```
[VOICE_TRACE] stage=WAKE_EVENT|WAKE_GATE|STT_RESULT|NORMALIZED_TEXT|INTENT_MATCH|ACTION_DISPATCH|BARGE_IN|FINAL_RESPONSE result=...
```

Ao investigar voz, esses prints são a primeira fonte. Ao adicionar estágio novo, seguir o
mesmo formato para continuar grepável.

## Gates antes de empacotar

O Python da ZARA é `.venv\Scripts\python.exe`, criado por
`tools/preparar_python.py` a partir de um CPython autocontido em
`%LOCALAPPDATA%\ZARA3\toolchain\python`. Nunca usar `python` solto: até
2026-08-13 o PATH resolvia para o venv do Hermes, e a ZARA buildava dentro do
ambiente de outro projeto.

```
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check main.py core memory integrations tests build_exe.py
.venv\Scripts\python.exe -m compileall -q main.py core memory integrations tests build_exe.py
```

Usar o Python **do projeto**, por caminho explícito. Nunca o Python do Hermes.

## Proibido

- adicionar caminho de resposta que fale sucesso sem executor
- gatear ação local determinística atrás do Supercérebro
- divergir voz e texto
- remover `[VOICE_TRACE]` "para limpar log"
- mexer em `core/url_security.py` e nos gates de confirmação como efeito colateral
