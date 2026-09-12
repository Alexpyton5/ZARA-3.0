---
name: tracing-voice-pipeline
description: Diagnostica falhas de wake word, microfone, STT, intent, execução ou TTS na ZARA percorrendo o pipeline inteiro estágio por estágio com os marcadores [VOICE_TRACE] e comparando texto vs voz com a MESMA frase; use sempre que a ZARA não ouvir, não entender, não executar ou não falar.
---

# Trace do pipeline de voz

## Quando usar

- ZARA não acorda, acorda sozinha, ou entra em loop com a própria voz.
- STT transcreve errado, ou transcreve certo e nada acontece.
- Comando por texto funciona e o mesmo comando por voz falha (ou o inverso).
- Resposta sai muda, cortada, com voz errada, ou o barge-in não interrompe.

## Fluxo obrigatório

1. **Nomeie o estágio suspeito** antes de ler código. O trace é linear:
   `MIC → WAKE/MIC MANUAL → STT → NORMALIZAÇÃO → RENDERER → PRELOAD → IPC ELECTRON → SIDECAR →
   INTENT CANÔNICO → ACTION REGISTRY → EXECUTOR → READBACK → RESPOSTA → TTS`.
2. **Colete `[VOICE_TRACE]` primeiro.** O backend já emite
   `print("[VOICE_TRACE] stage=... result=...")` em `core/ipc_handlers.py`. Estágios observados:
   `WAKE_EVENT`, `WAKE_GATE`, `STT_RESULT`, `NORMALIZED_TEXT`, `INTENT_MATCH`, `ACTION_DISPATCH`,
   `BARGE_IN`, `FINAL_RESPONSE`. O último estágio que aparece é o ponto de corte. Comece por ele.
3. **Faça o diferencial texto-vs-voz com a MESMA frase, literalmente igual.** Digite a frase e
   depois fale a frase. Isso separa o problema em dois mundos:
   - falha só na voz → o defeito está antes do dispatcher (mic, wake, STT, normalização);
   - falha nos dois → o defeito está no dispatcher, intent, registry ou executor.
4. **Confirme que os dois caminhos convergem.** Texto entra por `handle_send_message`
   (`core/ipc_handlers.py`, ~linha 2055). Voz entra por `_process_voice_message` (~1341), chamado
   por `_on_speech_recognized` (~758) e por `_on_gemini_live_turn` (~676). Ambos percorrem a MESMA
   cadeia: `_try_jarvis_multi_action` → `_try_reminder_intent` → `_try_operational_memory_intent` →
   `_try_self_knowledge` → `_try_file_intent` → `_try_compound_pc_intent` → `_try_pc_intent` →
   guard `_looks_like_unhandled_local_action` → LLM. Divergência entre os dois é bug, não design.
5. **Se parou em `INTENT_MATCH`:** leia `core/pc_voice_intent.py` (`PcVoiceIntentDetector`).
   Confirme se a ação está em `_LOCAL_DETERMINISTIC_ACTIONS` — esse conjunto isenta ações locais do
   gate do Supercérebro. Reflexo local nunca pode depender do Supercérebro estar ligado.
6. **Se parou em `ACTION_DISPATCH`:** siga para `core/action_registry.py` e `core/actions/*.py`
   (`system.py`, `os_ops.py`, `media_apps.py`, `browser.py`, `files.py`, `windows_radios.py`,
   `vision.py`, `web.py`, `code.py`, `terminal.py`, `scheduler.py`).
7. **Se o problema é entrada ou saída de áudio:** `core/voice_stt.py`, `core/voice_tts.py`,
   `core/gemini_live_voice.py`.
8. **Uma hipótese, um patch pequeno, um build, um teste físico de voz.** Repetiu duas vezes sem
   resolver: `BLOCKED` com o trace capturado.

## Regras de evidência

- Trace real do runtime empacotado vale mais que leitura de código. Cole as linhas `[VOICE_TRACE]`.
- Ausência de um estágio no log é evidência. Diga qual estágio faltou.
- Só `VOICE_PHYSICAL` fecha bug de voz: Alex falou, a ZARA fez, Alex viu o Windows mudar.
- Registre sempre qual EXE produziu o trace (ver `validating-packaged-runtime`).
- Se adicionar instrumentação nova, mantenha o mesmo formato `[VOICE_TRACE] stage=... result=...`.

## O que NUNCA fazer

- Nunca declarar voz consertada com base em teste de texto. TEXT PASS + VOICE FAIL = falha.
- Nunca criar "ferramentas de voz" paralelas às de texto. Um request canônico, um dispatcher.
- Nunca pular estágios do trace por intuição — o estágio pulado costuma ser o quebrado.
- Nunca alterar a ordem da cadeia de intents como efeito colateral de outro conserto.
- Nunca remover ou silenciar linhas `[VOICE_TRACE]` existentes.
- Nunca tratar "o STT transcreveu certo" como prova de que a ação executou.
