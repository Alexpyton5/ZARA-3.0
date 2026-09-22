# Arquitetura recomendada
- Use Gemini Live native audio com wake word desabilitado por padrão (transcrição contínua) para permitir barge-in real. [source: core/gemini_live_voice.py:6-10]
- Manter o modo de transporte de áudio como "renderer" (Electron/Chromium AEC) para cancelamento de eco sem necessidade de processamento adicional. [source: core/gemini_live_voice.py:135-139]
- Configurar VAD do Gemini Live com `silence_duration_ms` entre 150ms e 200ms para reduzir latência de fechamento de turno, mantendo sensibilidade alta (`end_of_speech_sensitivity: END_SENSITIVITY_HIGH`). [source: core/gemini_live_voice.py:154-156; docs/auditoria_voz_reverso.md:4]
- Implementar supressão de ruído cliente-side (ex: WebRTC NS) somente quando o transporte de áudio for "local" (PortAudio) para melhorar SNR antes do VAD do servidor. [source: docs/auditoria_voz_reverso.md:5]
- Manter filtro de eco baseado em conteúdo (`looks_like_assistant_echo`) como primeira linha de defesa, complementado por um modelo leve de supressão de ruído neural (ex: RNNoise) em ambientes ruidosos. [source: docs/auditoria_voz_reverso.md:6]
- Manter a janela de conversa (gemini_wake_armed_until) configurável via `api_keys.json` (ex: 3s) para reduzir falsos positivos de wake word em diálogos prolongados. [source: core/ipc_handlers.py:_WAKE_PREFIX_RE logic; docs/auditoria_voz_reverso.md:7]
- Garantir que o interrupt_speech() limpe as filas de áudio e de fala e redefina o estado para LISTENING imediatamente após barge-in. [source: docs/auditoria_voz_reverso.md:8]

# Gaps da ZARA hoje
- VAD padrão configurado em 300ms (`vad_silencio_ms`) pode introduzir latência excessiva na detecção de fim de fala, especialmente em respostas curtas. [source: core/gemini_live_voice.py:154-156; docs/auditoria_voz_reverso.md:11]
- Ausência de supressão de ruído cliente-side no modo de áudio "local" (PortAudio) deixa o microfone suscetível a ruído de ambiente, reduzindo a acurácia do VAD do servidor. [source: docs/auditoria_voz_reverso.md:12]
- Janela de conversa atualmente pode ser longa (padrão não especificado no código, mas provavelmente alguns segundos) levando a ativações acidentais por fala de TV ou conversas de fundo. [source: docs/auditoria_voz_reverso.md:13]
- Filtro de eco baseado apenas em similaridade de conteúdo pode falhar quando houver sobreposição de fala com ruído elevado ou quando o eco é atenuado demais para ser reconhecido. [source: docs/auditoria_voz_reverso.md:14]
- Não há mecanismo de ajuste dinâmico do VAD com base no nível de ruído estimado (adaptativo). [source: docs/auditoria_voz_reverso.md:15]

# Libs recomendadas
- `webrtcvad` (ou o VAD nativo do WebRTC via `aiortc` ou `PyAudioAnalysis`) para detetor de atividade de voz cliente-side caso queira fazer pré-filtragem antes de enviar ao Gemini Live. [source: docs/auditoria_voz_reverso.md:18]
- `webrtcns` (WebRTC Noise Suppression) ou `rnnoise` via bindings Python para redução de ruído em tempo real no modo local. [source: docs/auditoria_voz_reverso.md:19]
- `numpy` e `scipy` para processamento de áudio se for implementar filtros customizados. [source: docs/auditoria_voz_reverso.md:20]
- `pydub` ou `soundfile` para leitura/gravação de áudio em testes. [source: docs/auditoria_voz_reverso.md:21]
- `prometheus-client` para exportar métricas de telemetria (contadores de turnos, latências, erros de VAD, etc.). [source: docs/auditoria_voz_reverso.md:35]

# Config de VAD ótima
- Valor recomendado: `200ms` (equilíbrio entre latência e robustez). [source: docs/auditoria_voz_reverso.md:24]
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
  [source: docs/auditoria_voz_reverso.md:26-33]
- Além disso, recomenda-se definir `end_of_speech_sensitivity: END_SENSITIVITY_HIGH` (já é padrão no código via `types.EndSensitivity.END_SENSITIVITY_HIGH` quando `vad_fim_sensivel=True`). [source: docs/auditoria_voz_reverso.md:36]

# Fontes
- Código fonte da ZARA 3.0 CLEAN 002: `core/gemini_live_voice.py` (linhas 1-1481) – demonstra configuração de VAD, wake word, áudio transport, barge-in. [source: file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/core/gemini_live_voice.py]
- Código fonte da ZARA 3.0 CLEAN 002: `core/ipc_handlers.py` (linhas 1-1911) – demonstra wake prefix, janela de conversa, filtro de eco, tratamento de interrupção. [source: file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/core/ipc_handlers.py]
- Testes de responsividade e barge-in: `tests/test_gemini_live_voice_responsiveness.py`, `tests/test_voice_barge_in.py` (todos passaram). [source: file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/tests/test_gemini_live_voice_responsiveness.py]
- Testes de latência VAD: `tests/test_voice_latency_vad.py` (valida que `vad_silencio_ms` está dentro de faixa segura). [source: file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/tests/test_voice_latency_vad.py]
- Documentação oficial do Gemini Live API sobre `RealtimeInputConfig.AutomaticActivityDetection` e `silence_duration_ms`: https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/models/multimodal-live [source: web]
- Discussão da comunidade sobre ajuste de VAD para falas curtas: https://discuss.ai.google.dev/t/suddenly-the-gemini-live-api-stopped-understanding-input-audio/103496 [source: web]
- Guia da API Gemini Live (GeminiEx) mostrando estrutura de `realtime_input_config`: https://hexdocs.pm/gemini_ex/live_api.html [source: web]