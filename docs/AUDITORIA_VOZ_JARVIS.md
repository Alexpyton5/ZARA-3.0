# Auditoria de voz estilo JARVIS na ZARA 3.0

## 1. Arquitetura recomendada

- Use Gemini Live native audio com wake word desabilitado por padrão (transcrição contínua) para permitir barge-in real.
- Manter o modo de transporte de áudio como "renderer" ( Electron/Chromium AEC ) para cancelamento de eco sem necessidade de processamento adicional.
- Configurar VAD do Gemini Live com `silence_duration_ms` entre 150ms e 200ms para reduzir latência de fechamento de turno, mantendo sensibilidade alta (`end_of_speech_sensitivity: END_SENSITIVITY_HIGH`).
- Implementar supressão de ruído cliente-side (ex: WebRTC NS) somente quando o transporte de áudio for "local" (PortAudio) para melhorar SNR antes do VAD do servidor.
- Manter filtro de eco baseado em conteúdo (`looks_like_assistant_echo`) como primeira linha de defesa, complementado por um modelo leve de supressão de ruído neural (ex: RNNoise) em ambientes ruidosos.
- Manter a janela de conversa (gemini_wake_armed_until) configurável via `api_keys.json` (ex: 3s) para reduzir falsos positivos de wake word em diálogos prolongados.
- Garantir que o interrupt_speech() limpe as filas de áudio e de fala e redefina o estado para LISTENING imediatamente após barge-in.

## 2. Gaps da ZARA hoje

- VAD padrão configurado em 300ms (`vad_silencio_ms`) pode introduzir latência excessiva na detecção de fim de fala, especialmente em respostas curtas.
- Ausência de supressão de ruído cliente-side no modo de áudio "local" (PortAudio) deixa o microfone suscetível a ruído de ambiente, reduzindo a acurácia do VAD do servidor.
- Janela de conversa atualmente pode ser longa (padrão não especificado no código, mas provavelmente alguns segundos) levando a ativações acidentais por fala de TV ou conversas de fundo.
- Filtro de eco baseado apenas em similaridade de conteúdo pode falhar quando houver sobreposição de fala com ruído elevado ou quando o eco é atenuado demais para ser reconhecido.
- Não há mecanismo de ajuste dinâmico do VAD com base no nível de ruído estimado (adaptativo).

## 3. Libs recomendadas

- `webrtcvad` (ou o VAD nativo do WebRTC via `aiortc` ou `PyAudioAnalysis`) para detetor de atividade de voz cliente-side caso queira fazer pré-filtragem antes de enviar ao Gemini Live.
- `webrtcns` (WebRTC Noise Suppression) ou `rnnoise` via bindings Python para redução de ruído em tempo real no modo local.
- `numpy` e `scipy` para processamento de áudio se for implementar filtros customizados.
- `pydub` ou `soundfile` para leitura/gravação de áudio em testes.

## 4. Config de VAD ótima

Conforme observado no código (`core/gemini_live_voice.py` linhas 794-807) e nos testes (`tests/test_voice_latency_vad.py`), o parâmetro `vad_silencio_ms` controla o silêncio necessário para considerar o fim da fala. Valores muito altos aumentam latência; muito baixo pode cortar falas com pausas naturais.

- **Valor recomendado:** `200ms` (equilíbrio entre latência e robustez).
- Pode ser ajustado em `api_keys.json`:
  ```json
  {
    "vad_silencio_ms": 200,
    "vad_padding_ms": 100,
    "vad_fim_sensivel": true,
    "wake_word_mode": "disabled",
    "audio_transport": "renderer"
  }
  ```
- Além disso, recomenda-se definir `end_of_speech_sensitivity: END_SENSITIVITY_HIGH` (já é padrão no código via `types.EndSensitivity.END_SENSITIVITY_HIGH` quando `vad_fim_sensivel=True`).

## 5. Fontes

- Código fonte da ZARA 3.0 CLEAN 002: `core/gemini_live_voice.py` (linhas 1-1481) – demonstra configuração de VAD, wake word, áudio transport, barge-in. [source: file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/core/gemini_live_voice.py]
- Código fonte da ZARA 3.0 CLEAN 002: `core/ipc_handlers.py` (linhas 1-1911) – demonstra wake prefix, janela de conversa, filtro de eco, tratamento de interrupção. [source: file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/core/ipc_handlers.py]
- Testes de responsividade e barge-in: `tests/test_gemini_live_voice_responsiveness.py`, `tests/test_voice_barge_in.py` (todos passaram). [source: file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/tests/test_gemini_live_voice_responsiveness.py]
- Testes de latência VAD: `tests/test_voice_latency_vad.py` (valida que `vad_silencio_ms` está dentro de faixa segura). [source: file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/tests/test_voice_latency_vad.py]
- Documentação oficial do Gemini Live API sobre `RealtimeInputConfig.AutomaticActivityDetection` e `silence_duration_ms`: https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/models/multimodal-live [source: web]
- Discussão da comunidade sobre ajuste de VAD para falas curtas: https://discuss.ai.google.dev/t/suddenly-the-gemini-live-api-stopped-understanding-input-audio/103496 [source: web]
- Guia da API Gemini Live (GeminiEx) mostrando estrutura de `realtime_input_config`: https://hexdocs.pm/gemini_ex/live_api.html [source: web]