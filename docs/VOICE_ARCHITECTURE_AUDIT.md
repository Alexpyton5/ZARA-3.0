# Auditoria de Voz estilo JARVIS da ZARA

## 1. Arquitetura recomendada

- Use Gemini Live native audio com wake word desabilitado por padrão (transcrição contínua) para permitir barge-in real. (source: docs/AUDITORIA_VOZ_JARVIS.md#5, gemini_live_voice.py lines 6-27)
- Manter janela de conversa (gemini_wake_armed_until) configurável via api_keys.json para reduzir falsos positivos em diálogos prolongados. (source: docs/AUDITORIA_VOZ_JARVIS.md#10, ipc_handlers.py:_WAKE_PREFIX_RE logic)
- Audio transport: modo "renderer" (Electron/WebAudio) para ativar AEC do Chromium e cancelar eco; modo "local" para fallback. (source: gemini_live_voice.py lines 135-141, 964-970)
- VAD configurável: vad_silencio_ms, vad_padding_ms, vad_fim_sensivel via api_keys.json. (source: gemini_live_voice.py lines 154-156, tests/test_voice_latency_vad.py)
- Echo cancellation por conteúdo via looks_like_assistant_echo e detecção explícita de barge-in (is_explicit_human_barge_in). (source: gemini_live_voice.py lines 74-122, 59-71)
- Barge-in real: interrupt_speech acionado quando servidor detecta interrupção (interrupted flag). (source: gemini_live_voice.py lines 1104-1122, tests/test_voice_barge_in.py)
- Wake word híbrido: gate Vosk local pode ser ligado via "wake_word_mode": "local" em api_keys.json, mas por padrão está desligado. (source: gemini_live_voice.py lines 175-176, docs/ZARA-BASELINE-AUDIT-001.md#31)

## 2. Gaps da ZARA hoje

- Ausência de métricas de confiabilidade de wake word (taxa de acerto, latência de detecção). (source: docs/AUDITORIA_VOZ_JARVIS_CONTINUIDADE6.md#25 [INFERENCIA])
- Falta de documento explicando trade‑offs da ativação do gate Vosk local (impacto no barge‑in e latência). (source: docs/AUDITORIA_VOZ_JARVIS_CONTINUIDADE86.md#62)
- Testes de unidade limitados para componentes de voz (ex: VAD config, wake word detection, echo filter). (source: observação dos testes existentes: apenas test_voice_barge_in.py e test_voice_latency_vad.py)
- Nenhum teste de carga ou simulação de ruído para validar barge‑in em condições adversas.
- Configuração de VAD não possui validação de valores extremos além do containment test (test_valor_do_arquivo_e_contido_em_faixa_segura). Não há teste de comportamento real com diferentes silêncios.

## 3. Libs recomendadas

- webrtcvad: alternativa leve ao Silero VAD para controle mais granular de atividade de voz (se necessário mudar de VAD). (não usado atualmente, mas mencionado como opção em alguns projetos)
- vosk: já usado para wake word gate local; garantir versão >=0.3.45 (source: docs/ZARA-BASELINE-AUDIT-001.md#194)
- sounddevice: já usado para captura e reprodução de áudio (source: gemini_live_voice.py line 732)
- numpy: usado para cálculo de nível de áudio (source: gemini_live_voice.py line 1444)
- google-genai: já usado para Gemini Live API (source: gemini_live_voice.py line 745)

## 4. Config de VAD ótima

Baseado nos testes e comentários:

- vad_silencio_ms: 300 ms (padrão) – suficientemente curto para não parecer travado, mas longo o suficiente para não cortar frase no meio. (source: tests/test_voice_latency_vad.py: test_padrao_e_mais_rapido_que_um_segundo, test_valor_do_arquivo_e_contido_em_faixa_segura)
- vad_padding_ms: 100 ms (padrão) – garante que a fala não seja cortada abruptamente no fim.
- vad_fim_sensivel: True (padrão) – aumenta sensibilidade no fim da fala para detecção mais precoce, mas ainda conservadora.

Esses valores são ajustáveis sem rebuild via api_keys.json.

## 5. Fontes

- gemini_live_voice.py: C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\core\gemini_live_voice.py – linhas específicas citadas.
- ipc_handlers.py: C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\core\ipc_handlers.py – linhas 31-43 (_WAKE_PREFIX_RE).
- tests/test_voice_barge_in.py: C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\tests\test_voice_barge_in.py.
- tests/test_voice_latency_vad.py: C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\tests\test_voice_latency_vad.py.
- docs/AUDITORIA_VOZ_JARVIS.md: C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\docs\AUDITORIA_VOZ_JARVIS.md.
- docs/AUDITORIA_VOZ_JARVIS_CONTINUIDADE6.md: C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\docs\AUDITORIA_VOZ_JARVIS_CONTINUIDADE6.md.
- docs/AUDITORIA_VOZ_JARVIS_CONTINUIDADE86.md: C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\docs\AUDITORIA_VOZ_JARVIS_CONTINUIDADE86.md.
- docs/ZARA-BASELINE-AUDIT-001.md: C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\docs\ZARA-BASELINE-AUDIT-001.md.
- docs/RECOMENDACOES-VOZ.md: C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\docs\RECOMENDACOES-VOZ.md.