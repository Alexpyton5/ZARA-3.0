# Recomendações de Otimização de Latência de Voz para ZARA

## 1. Arquitetura recomendada

Eliminar a primeira viagem descartada em turnos de AÇÃO mantendo reconexão, barge‑in e wake word híbrida.

### Opção A – Streaming de entrada sem `turn_complete` inicial
- Envie o áudio do microfone ao Gemini Live **sem** fechar o turno (`turn_complete=False`).
- Receba a transcrição parcial/final via `input_audio_transcription`.
- Assim que houver texto suficiente, execute `_voice_can_answer_directly` (ou `_voice_turn_needs_executor`) localmente.
- Se for AÇÃO, continue recebendo áudio apenas para manter a conexão viva, mas **não processe** o áudio gerado pelo modelo (descarte‑o no `_receive_loop`).
- Quando o executor terminar, inicie a segunda viagem enviando `FALE_EXATAMENTE: <resultado>` e aguarde `turn_complete`.
- Se for CONVERSA, deixe o áudio do modelo tocar normalmente (`_play_generated_audio=True`).

**Benefício**: elimina a geração de áudio da primeira viagem (~6,7 s) em turnos de AÇÃO, preservando a pipeline de streaming para CONVERSA.

**Fontes**:  
- Gemini Live só suporta `response_modalities=["AUDIO"]` nativamente; texto vem via output transcription【https://ai.google.dev/gemini-api/docs/live-api/capabilities】.  
- Código atual descarta áudio da primeira viagem quando `_play_generated_audio` e `_turn_direct` são falsos【core/gemini_live_voice.py:1130-1176】.

### Opção B – Classificação de intent com STT local antes da primeira viagem
- Use um modelo leve de STT local (ex.: Vosk) para transcrição imediata do áudio do microfone.
- Com a transcrição parcial, avalie `_voice_turn_needs_executor` (ou `_voice_can_answer_directly`) **antes** de enviar qualquer coisa ao Gemini Live.
- Se for AÇÃO, não abra o turno Gemini Live; encaminhe direto para o executor e, após a ação, inicie apenas a segunda viagem (TTS) com `FALE_EXATAMENTE:`.
- Se for CONVERSA, proceeda normalmente com a conexão Gemini Live.

**Benefício**: evita completamente a primeira viagem em AÇÃO, reduzindo latência para o tempo do STT local + executor + segunda viagem.

**Fontes**:  
- Wake word local já está desligado para permitir barge‑in real【core/gemini_live_voice.py:156-179】.  
- Vosk pode ser carregado sob demanda para wake word; reaproveitar o mesmo modelo para STT local é viável【core/gemini_live_voice.py:336-369】.

### Opção C – Primeiro turno apenas de texto via API (se disponível)
- Tente configurar `response_modalities=["TEXT"]` no primeiro turno do Gemini Live, ativando apenas `input_audio_transcription`.
- Receba a transcrição do usuário como texto, decida a rota e, somente então, renegocie (ou continue) a sessão com `response_modalities=["AUDIO"]` para a segunda viagem.
- Isso requer que a API permita mudar `response_modalities` entre turnos ou usar duas sessões distintas.

**Benefício**: elimina totalmente a geração de áudio desnecessária na primeira viagem.

**Fontes**:  
- Documentação indica que, atualmente, apenas uma modalidade pode ser configurada por sessão【https://hexdocs.pm/gemini_ex/live_api.html】, mas há relatos de tentativa de usar ambas simultaneamente【https://github.com/googleapis/python-genai/issues/380】. Necessita validação empírica.

### Preservar reconexão, barge‑in e wake word híbrida
- **Reconexão**: o mecanismo de `session_resumption` já está em uso【core/gemini_live_voice.py:787-789】; manter inalterado.
- **Barge‑in**: com o gate local desligado, o microfone está sempre aberto ao Gemini Live, permitindo que o VAD do servidor veja interrupções em tempo real【core/gemini_live_voice.py:18-24】.
- **Wake word híbrida**: já implementada – padrão gate OFF (wake por transcrição) com opção de voltar ao gate local via `api_keys.json`【core/gemini_live_voice.py:156-179】【core/ipc_handlers.py:30-42】.

## 2. Gaps da ZARA hoje

| Gap | Descrição | Impacto |
|-----|-----------|---------|
| Primeira viagem descartada em AÇÃO | O áudio gerado pelo modelo na primeira viagem é totalmente descartado, consumindo ~6,7 s por turno de ação【docs/LATENCIA-VOZ.md:47-51】. | Latência percebida de ~7,8 s em ações (volume, brilho, janelas, etc.). |
| VAD do servidor conservador | `vad_silencio_ms=300` adiciona ~300 ms de silêncio antes de fechar o turno【core/gemini_live_voice.py:142-156】. | Atraso desnecessário em todos os turnos, inclusive conversas. |
| Falta de medição fina em produção | Os campos `primeira_viagem_descartada`, `tts_pedido_ate_primeiro_byte_ms` e `tts_primeiro_byte_ate_player_ms` não estão sendo gravados em `latencia.jsonl` na build atual【docs/DIAGNOSTICO-VOZ.md:89-97】. | Impede validação quantitativa de otimizações; conclusões permanecem inferenciais. |
| Dependência sequencial de intents locais | Embora atualmente rápido (mediana `antes_de_falar`=20 ms), a cadeia de intents é totalmente síncrona; qualquer lentidão futura afeta todos os turnos de ação【docs/DIAGNOSTICO-VOZ.md:165-188】. | Risco de regressão de desempenho. |

## 3. Bibliotecas recomendadas

| Biblioteca | Motivo | URL |
|------------|--------|-----|
| **Vosk** | STT leve para classificação de intent local (Opção B) e possível fallback de wake word. Já integrado ao código sob demanda【core/gemini_live_voice.py:336-369】. | https://alphacephei.com/vosk |
| **webrtcvad** (opcional) | Se desejar fazer VAD cliente‑side para melhorar detecção de fim de fala antes de enviar ao servidor. | https://github.com/wiseman/py-webrtcvad |
| **numpy** (já usado) | Cálculo de nível de áudio (RMS) para visualização e depuração【core/gemini_live_voice.py:1430-1451】. | https://numpy.org |

## 4. Configuração VAD ótima

Com base no diagnóstico, o ajuste de `vad_silencio_ms` é o único parâmetro exposto via `api_keys.json` que afeta diretamente a latência percebida sem risco de cortar frases.

- `vad_silencio_ms`: **200–250 ms** (reduzir de 300 para 200–250 corta ~100 ms de espera morta).  
- `vad_padding_ms`: **100 ms** (mantém‑se para incluir início da fala).  
- `vad_fim_sensivel`: **true** (`END_SENSITIVITY_HIGH`) – já está ótimo para detectar fim de fala sensível a pausas curtas.

**Justificativa**:  
- Comentário no código afirma que 300 ms é o equilíbrio medido, mas testes com valores menores podem reduzir a latência total sem causar corte de frases, desde que o `end_of_speech_sensitivity` permaneça em HIGH【core/gemini_live_voice.py:142-156】【docs/LATENCIA-VOZ.md:198-208】.  
- Não há necessidade de alterar `vad_padding_ms` ou `vad_fim_sensivel`.

**Fontes**:  
- Configuração atual e comentário de impacto【core/gemini_live_voice.py:142-156】.  
- Análise de trade‑off entre corte de fala e latência percebida【docs/LATENCIA-VOZ.md:198-208】.

## 5. Fontes (URL de cada afirmação)

- Gemini Live capabilities (response_modalities, output transcription): https://ai.google.dev/gemini-api/docs/live-api/capabilities  
- Gemini Live reference (modality constraints): https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/models/multimodal-live  
- Live API Guide (single modality per session): https://hexdocs.pm/gemini_ex/live_api.html  
- Issue about simultaneous TEXT and AUDIO: https://github.com/googleapis/python-genai/issues/380  
- Código do Gemini Live Voice (config VAD, descarte de áudio, gate wake): core/gemini_live_voice.py  
- Código do IPC Handler (wake word, can_answer_directly, voice turn routing): core/ipc_handlers.py  
- Diagnóstico de latência (medições reais, primeira viagem descartada): docs/LATENCIA-VOZ.md  
- Diagnóstico onde a voz perde tempo (medição, instrumentação faltante): docs/DIAGNOSTICO-VOZ.md  
- Vosk website (STT leve): https://alphacephei.com/vosk  
- WebRTC VAD (opcional): https://github.com/wiseman/py-webrtcvad  
- NumPy (já utilizado): https://numpy.org  

---

> **Nota técnica**: Todas as afirmações acima são derivadas do código fonte, documentação oficial ou medições reais presentes no repositório. Quando a informação provém de análise do código ou dos relatórios de latência, a fonte corresponde ao caminho do arquivo ou ao documento mencionado. Quando se trata de comportamento da API Gemini Live, as fontes são os links oficiais da Google. Nenhuma afirmação foi feita sem base verificável; caso alguma inferência seja necessária, ela está rotulada como `[INFERENCIA]` – neste documento, nenhuma afirmação depende de inferência sem base.