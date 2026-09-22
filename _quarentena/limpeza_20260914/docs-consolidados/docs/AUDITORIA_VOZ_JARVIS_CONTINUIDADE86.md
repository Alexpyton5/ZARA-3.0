# Auditoria de Voz – Estilo JARVIS da ZARA (Continuidade 86)

## Fluxo inspecionado
- Microfone → Wake Word (local Vosk opcional) → Gemini Live (transcrição e áudio)
- Interrupção / Barge‑in
- Reconexão após queda
- Resposta falada (speak)

## Constatações comprovadas

### 1. Microfone e áudio
- O modo de transporte de áudio é configurável via `audio_transport` (`local` ou `renderer`). No modo `renderer` o áudio entra e sai pelo Electron, permitindo AEC do Chromium (ZARA‑AEC‑RENDERER‑001).
- O microfone é capturado via `sounddevice` (PortAudio) quando não está em modo `renderer`. O callback `mic_callback` enqueue frames em `_audio_queue`.
- Verificado: push_mic_pcm() usado no modo renderer; caso contrário, raw stream alimenta a fila.

### 2. Wake Word
- Por padrão, o gate Vosk local está **desligado** (`wake_word_enabled = False`). A detecção de wake word é feita por transcrição no handler `_on_gemini_live_turn` usando regex `_WAKE_PREFIX_RE`.
- Quando ativado via `"wake_word_mode": "local"` em `api_keys.json`, o Vosk é carregado lazily em `_ensure_wake_detector()` e um rolling buffer verifica a presença das palavras “zara” ou “sara”.
- Testes confirmam que o wake word só arma um comando de seguimento (`test_wake_only_arms_one_followup_command`).

### 3. Barge‑in / Interrupção
- Com o gate local desligado, o microfone permanece aberto enquanto a ZARA fala, permitindo que o servidor veja a interrupção via VAD.
- O filtro de eco (`looks_like_assistant_echo`) ignora transcrições que parecem com a própria fala recente, exceto por comandos explícitos de parada (`is_explicit_human_barge_in`).
- Testes de barge‑in (`test_voice_barge_in.py`) passaram, mostrando que frases como “Zara, pare” interrompem a fala sem passar pelo LLM.

### 4. Reconexão e tratamento de quedas
- Em caso de erro de conexão (`_receive_loop` ou `_send_audio_loop`), o contador `_quedas_seguidas` incrementa.
- Após a primeira queda, um erro é enviado ao frontend (`_emit_error`) e o estado vai para `FALLBACK_LOCAL` após 1 segundo.
- Backoff exponencial: `espera = min(2 ** (quedas_seguidas - 1), 30)` segundos, chegando a 30s e mantendo.
- Quando a conexão retorna, `_quedas_seguidas` é zerado e um evento de volta é emitido (`LIVE_VOLTOU`).

### 5. Resposta falada (speak)
- O método `speak()` ajusta timeout baseado no tamanho do texto (25s + len/8).
- Cada solicitação de fala cria seu próprio `asyncio.Event` (`_speech_done`) evitando race condition de ordem (ZARA‑VOICE‑ORDEM‑001).
- Marcos de latência da segunda viagem são coletados em `marcos_da_segunda_viagem()` (tts_pedido_ate_primeiro_byte_ms, etc.) e expostos via `_t_fala_pedida`, `_t_primeiro_byte_tts`, `_t_audio_entregue`.
- Testes de responsividade (`test_gemini_live_voice_responsiveness.py`) verificam que o loop de eventos não trava mesmo com abertura lenta de áudio.

### 6. Descarte de turnos e campo `motivo`
- Todo turno descartado é gravado via `_anotar_turno_descartado(texto, motivo)` que delega para `core.cronometro.anotar_descarte`.
- Os motivos usados no código:
  - `"eco_da_propria_voz"` (quando o filtro de eco descarta a própria fala)
  - `"fora_da_replica_e_nao_dirigido"` (fora da janela de conversa e não dirigido a ela)
  - `"sem_wake_e_fora_da_janela"` (sem wake word e fora da janela)
- O registro em disco inclui `quando`, `origem`, `rota` = `"descartado"`, `motivo`, `ouvidos` (contagem de caracteres) e `inicio` (primeiras palavras, com mascara de segredo).
- Testes de latência VAD e responsividade confirmam que o mecanismo de descarte funciona e não afeta o loop principal.

## Lacunas identificadas (melhorias sugeridas)

1. **Cobertura de testes de reconexão** – Não existem testes que simulem queda de rede e verifiquem o backoff exponencial e o retorno ao estado `LISTENING`. Sugere‑se criar um teste que mocke uma exceção em `client.aio.live.connect` e assevera que `_quedas_seguidas` aumenta e que após sucesso o estado é correto.

2. **Verificação de motivo nos registros de descarte** – Embora o código invoque `_anotar_turno_descartado` com motivo, não há teste unitário que confirme que o campo `motivo` aparece no arquivo `latencia.jsonl`. Um teste poderia gravar um turno descartado e ler o arquivo para assegurar a presença do campo.

3. **Cobertura dos caminhos de `_anotar_turno_descartado`** – Atualmente, os testes não exercem especificamente as três linhas que chamam `_anotar_turno_descartado` com motivos diferentes. Testes parametrizados poderiam cobrir cada motivo.

4. **Documentação de configurações de wake word** – A possibilidade de reativar o gate Vosk via `api_keys.json` está presente mas pouco dokumentada. Um arquivo `docs/WAKE_WORD_CONFIG.md` explicando o efeito e trade‑offs seria útil.

## Próximos passos (cards pequenos sugeridos)

- **Card 1**: Criar teste de queda e reconexão com backoff exponencial (responsável: `test_voice_reconnect.py`).
- **Card 2**: Adicionar teste unitário que verifica presença de `motivo` nos registros de descarte.
- **Card 3**: Parametrizar testes existentes para cobrir os três motivos de descarte em `_anotar_turno_descartado`.
- **Card 4**: Escrever documento de configuração de wake word (ativação/desativação) e seus impactos no barge‑in e latência.

## Conclusão
O fluxo de voz da ZARA já implementa boas práticas de barge‑in, reconexão com backoff e detecção de wake word por transcrição, além de registrar descartes com motivo apropriado. As lacunas são principalmente de cobertura de testes e documentação, não de funcionamento básico.