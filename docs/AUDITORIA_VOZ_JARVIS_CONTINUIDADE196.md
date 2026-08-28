# Auditoria de Voz Estilo JARVIS da ZARA [continuidade 196]

## Fluxo Inspecionado
- Microfone
- Wake Word
- Interrupção/Barge-in
- Reconexão
- Resposta Falada

## Lacunas Encontradas

### 1. Ausência de mecanismo de reconexão com backoff exponencial
- **Caminho**: `core/gemini_live_voice.py`
- **Símbolos**: `start`, `_receive_loop`, `_open_streams` (referenciado em teste obsoleto)
- **Prova**: 
  - Nas linhas 667-726 (método `start`) não há lógica de repetição em caso de falha de conexão além de um único tentativo.
  - No `_receive_loop` (linhas 833-983) não há tratamento de exceções de rede que possa disparar uma reconexão.
  - O teste `tests/test_gemini_live_voice_responsiveness.py::test_blocked_audio_open_times_out_without_blocking_event_loop` falha porque tenta mockar `_open_streams` que não existe mais, indicando que o código de tratamento de erro de inicialização pode estar desatualizado.

### 2. Tratamento de erro de rede limitado no recebimento de mensagens
- **Caminho**: `core/gemini_live_voice.py`
- **Símbolos**: `_receive_loop`, `session_resumption_update`
- **Prova**:
  - Linhas 839-843 tratam apenas de atualização do `session_handle` em caso de `session_resumption_update`, mas não há tratamento de `go_away` (linha 845) além de sair do loop, o que encerra a sessão sem tentar reconectar.
  - Não há detecção de outras condições de erro (como timeout de leitura) que possam ocorrer durante `async for response in session.receive():`.

### 3. Falta de limite explícito de tentativas de reconexão e backoff
- **Caminho**: `core/gemini_live_voice.py`
- **Símbolos**: Nenhuma implementação encontrada
- **Prova**: Busca por "reconnect", "retry", "backoff" retorna zero resultados em todo o código de voz.

## Cartões Sugeridos

### Card 1: Implementar reconexão com backoff exponencial
- **Descrição**: Adicionar lógica ao método `start` e/ou `_receive_loop` para tentar reconectar com atraso crescente em caso de falhas de rede ou sessão encerrada inesperadamente.
- **Critérios de Aceitação**:
  - Após 3 tentativas falhas, o sistema deve parar e emitir um evento de erro.
  - O atraso inicial deve ser de 1 segundo, dobrando a cada tentativa até um máximo de 10 segundos.
  - Deve respeitar o estado `_stop` para não tentar reconectar após parada intencional.

### Card 2: Atualizar teste de timeout de inicialização
- **Descrição**: Corrigir o teste `test_blocked_audio_open_times_out_without_blocking_event_loop` para mockar os métodos corretos de inicialização de streams (`_ensure_input_stream` e `_ensure_output_stream`) ou remover se obsoleto.
- **Critérios de Aceitação**:
  - O teste deve passar novamente.
  - Deve continuar verificando que o event loop não é bloqueado durante a tentativa de inicialização com timeout.

### Card 3: Adicionar tratamento de erro de sessão para disparar reconexão
- **Descrição**: No `_receive_loop`, ao detectar condições como `go_away` ou exceções de rede, iniciar um processo de reconexão em vez de simplesmente encerrar.
- **Critérios de Aceitação**:
  - Ao receber `go_away`, o cliente deve tentar reconectar após um curto atraso.
  - Qualquer exceção durante `session.receive()` deve ser capturada e levar à mesma lógica de reconexão.
  - Deve evitar loops infinitos de reconexão em caso de falha persistente (usar o mesmo backoff do Card 1).

## Evidências Adicionais

### Fluxo de Microfone e Wake Word
- O wake word local (Vosk) está desativado por padrão (`wake_word_enabled: bool = False` linha 177).
- O wake é feito por transcrição no Gemini via `_WAKE_PREFIX_RE` em `ipc_handlers.py` (linhas 32-44).
- Isso permite barge-in real porque o microfone está sempre aberto para o Gemini (linhas 19-24 do docstring).

### Barge-in (Interrupção)
- O barge-in é tratado nas linhas 852-871: ao detectar `interrupted`, há flush de output, marcação de término de turno, reset de estado e emissão de estado LISTENING.
- O eco próprio é filtrado por `is_self_echo_transcript` (linhas 516-529) que usa `looks_like_assistant_echo` (linhas 75-123).

### Resposta Falada
- A fala é enviada via `speak` (linhas 560-586) que coloca o texto em uma fila e aguarda conclusão.
- O áudio do modelo é recebido em `_receive_loop` (linhas 927-952) e enviado para o output stream ou para o Electron via `on_output_audio` dependendo do modo de transporte de áudio.