---
name: domar-eco-e-microfone
description: Resolve a ZARA se ouvindo, entrando em loop com a própria voz da Kore, cortando a fala do Alex ou não abrindo o microfone, tratando AEC do Chromium, wake gate, barge-in e escolha de dispositivo de entrada; use em qualquer sintoma de eco, auto-escuta, microfone mudo, barge-in que não corta ou ZARA respondendo a si mesma (Fase 1, prioridade 3).
---

# Domar eco e microfone

Prioridade 3 da Fase 1. Sintoma típico: a ZARA fala, se escuta, responde ao próprio áudio,
e o turno nunca fecha.

## Fato já medido (não re-testar do zero)

O **AEC do Chromium resolve o eco** — cancelamento de eco acontece no renderer, com a
captura e a reprodução na mesma pipeline de áudio do Electron. Compilar WebRTC à parte
está **descartado**. Ver [[aec-do-chromium-resolve-eco]].

Consequência arquitetural, escrita em `core/gemini_live_voice.py`: só o modo `renderer`
cancela eco, porque o AEC precisa que a voz da Kore **saia pelo mesmo contexto de áudio**
que captura o microfone. Se a Kore tocar por PortAudio/sounddevice no Python, o AEC não vê
o sinal de referência e o eco volta. **Não reintroduzir saída de áudio pelo Python.**

## Mapa dos arquivos

- `frontend/src/renderer/lib/aecAudio.ts`
  - `iniciarAudioAec()` — `getUserMedia` com `echoCancellation: true`,
    `noiseSuppression: false`, `autoGainControl: false`; confere o resultado real via
    `track.getSettings().echoCancellation`
  - `paraInt16em16k()` — reamostragem para 16 kHz antes de mandar ao backend
  - `tocarKore()` / `cortarKore()` — reprodução e corte imediato (barge-in de verdade)
- `core/gemini_live_voice.py`
  - `input_sample_rate = 16000`, `output_sample_rate = 24000`, `voice_name = "Kore"`,
    `model = "gemini-3.1-flash-live-preview"`
  - wake gate com Vosk (`vosk-model-small-pt-0.3`, senão `-en-us`); sem modelo, o gate
    degrada para streaming contínuo — que é justamente o estado que gera auto-escuta
- `core/ipc_handlers.py` — `_on_gemini_live_turn`, `handle_interrupt`, `_speak_response`

## Ordem de diagnóstico (não pular etapa)

1. **O AEC ligou mesmo?** `iniciarAudioAec` compara `getSettings().echoCancellation`.
   Se vier `false`, o navegador ignorou o pedido — nenhum ajuste posterior importa.
2. **Qual dispositivo abriu?** trace `MIC_DEVICE_ENUMERATION` e `SELECTED_INPUT_DEVICE`.
   Mudança de fone/headset troca o default do Windows e mata o AEC silenciosamente.
3. **O microfone abriu?** `MIC_OPEN_RESULT` — `TIMEOUT` aqui é problema de dispositivo,
   não de intent.
4. **Chegou áudio?** `AUDIO_FRAMES_RECEIVED result=PASS source=renderer`.
   Se a fonte não for `renderer`, o AEC está fora do caminho.
5. **É eco mesmo?** `ECHO_GUARD`, `ECHO_SUSPECT`, `SELF_ECHO` no trace.
6. **Barge-in corta o som?** `BARGE_IN` / `TURN_CANCELLED` + `cortarKore()`.
   Estado visual mudar sem o áudio parar é falso sucesso e é bug próprio.

O sidecar não grava log em arquivo: para ver o trace no build empacotado, abra o EXE por um
console (ver [[medir-latencia-da-zara]] para o comando de captura).

## Regras de mudança

- Um delta por vez: ou parâmetro de captura, ou wake gate, ou barge-in. Nunca os três.
- `noiseSuppression` e `autoGainControl` estão `false` **de propósito** — os dois
  distorcem o sinal de referência e pioram o AEC. Ligar qualquer um exige medição antes
  e depois, não intuição.
- Nunca "resolver" eco baixando o volume da Kore: mascara o defeito e piora o produto.
- Nunca desligar o wake gate para "testar mais fácil" e esquecer ligado.

## Prova de que foi resolvido

Só vale `VOICE_PHYSICAL`, com a Kore **audível no alto-falante** (não no fone):

1. "Zara, que horas são?" — ela responde e **não** dispara um segundo turno sozinha.
2. Falar por cima da resposta dela: o áudio corta na hora.
3. Deixar 30 s de silêncio com a ZARA ligada: nenhum turno fantasma aparece.

Teste com fone de ouvido **não prova** nada sobre eco: o caminho acústico não existe.
