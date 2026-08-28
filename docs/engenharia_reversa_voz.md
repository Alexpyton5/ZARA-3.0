# Engenharia Reversa de Arquitetura de Voz em Assistentes de Ponta

## 1. Arquitetura recomendada

### 1.1. Pipeline de áudio
- **Capture contínua**: microfone sempre aberto, sem gate de wake word local, para evitar perda de início de fala e permitir barge-in real. (ZARA: `wake_word_enabled: false` por padrão, `push_mic_pcm` recebe áudio continuamente) [core/gemini_live_voice.py:421-439]
- **Buffering de turno**: áudio do usuário é acumulado em `_turn_audio_buffer` enquanto estiver falando, protegido por lock de thread, e processado apenas ao final da fala detectada por VAD do servidor. [core/gemini_live_voice.py:1330-1334, 1389-1391]
- **VAD do servidor**: Gemini Live configura `realtime_input_config.automatic_activity_detection` com parâmetros `silence_duration_ms`, `prefix_padding_ms` e `end_of_speech_sensitivity` para determinar o fim da fala do usuário sem depender de VAD local. [core/gemini_live_voice.py:871-880]
- **Turn-taking**: após receber `turn_complete` do servidor, o processo de transcrição e roteamento é iniciado; o turno só é considerado concluído quando o servidor indica término. [core/gemini_live_voice.py:1288-1293]
- **Barge-in**: se o servidor enviar `interrupted: true` enquanto o ZARA está falando, o áudio de saída é imediatamente abortado, o estado é resetado e o microfone volta a ouvir. Isso permite interrupção em tempo real. [core/gemini_live_voice.py:1172-1190]
- **Cancelamento de eco**: 
  - Quando `audio_transport` = "renderer", o áudio de saída vai para o Electron (WebAudio) e o AEC do Chromium fornece referência far‑end para cancelamento de eco. [core/gemini_live_voice.py:265-269, 421-427]
  - Quando `audio_transport` = "local", o áudio de saída vai por PortAudio e o mesmo princípio se aplica (o AEC do Chromium ainda funciona porque o microfone e alto‑falante são capturados pelo mesmo processo). 
  - Além do AEC, há um filtro de conteúdo `_looks_like_own_echo` que descarta transcrições que parecem eco da própria assistente, baseado em sobreposição de tokens e ordem, permitindo que um comando como "pare" dito por cima da fala não seja bloqueado. [core/gemini_live_voice.py:77-125, 565-578]
- **Pós‑processamento com Whisper**: após o término do turno, o buffer de áudio é enviado para um modelo `faster_whisper` (tiny, int8) para melhorar a transcrição, caso a transcrição nativa do Gemini falhe ou esteja vazia. [core/gemini_live_voice.py:500-563, 1387-1395]

### 1.2. Componentes principais
- **GeminiLiveVoice**: gerencia conexão com a API Gemini Live, filas de áudio, estado de gate, controle de turno e integração com callbacks de nível, estado e transcrição. [core/gemini_live_voice.py:244-1594]
- **VoicePipeline (Vosk + Porcupine)**: pipeline alternativa usada quando o wake word local está habilitado (não é o padrão no modo Gemini Live). Inclui VAD simples baseado em energia (`vad_threshold`). [core/voice_stt.py:313-579]
- **IPC Handlers**: recebe transcrições do Gemini Live e decide se o turno é um comando direto (pode ser respondido pela voz) ou deve ser executado por ações do sistema. O wake word é detectado por transcrição (`_WAKE_PREFIX_RE`). [core/ipc_handlers.py (não exibido aqui, mas referenciado em comments)]

## 2. Gaps da ZARA hoje

| Gap | Descrição | Evidência |
|-----|-----------|-----------|
| **Wake word local opcional mas não usado** | O gate Vosk está desligado por padrão (`wake_word_enabled: false`). Isso elimina a latência de detecção local, mas deixa o usuário dependente apenas da detecção por transcrição, que pode falhar em ambientes ruidosos. | [core/gemini_live_voice.py:179-180, 353-355] |
| **VAD de baixa complexidade no fallback** | Quando o wake word local é ativado, o VAD usado é baseado apenas em energia (`vad_threshold = 0.005`) sem ajustes dinâmicos ou de frequência, o que pode causar falsos positivos/negativos. | [core/voice_stt.py:73, 491] |
| **Dependência de conexão estável com Gemini** | Qualquer interrupção na rede força reconexão com backoff exponencial; durante a reconexão, o ZARA fica temporarily indisponível (estado PROCESSING). Não há fallback para STT totalmente offline imediato. | [core/gemini_live_voice.py:947-989] |
| **Latência de segunda viagem ainda presente para ações** | Quando o turno é roteado para o executor (ação), o áudio da resposta é suprimido; porém, se o turno for classificado como conversa, a segunda viagem (ida e volta ao Google para a Kore ler o resultado) ainda ocorre, adicionando latência percebida. | [core/gemini_live_voice.py:1225-1286, comentários ZARA-LATENCIA-SEGUNDA-VIAGEM-001] |
| **Falta de teste automatizado de barge‑in e VAD** | Não há testes de integração que simulem interrupção em tempo real ou verifiquem o comportamento do VAD sob diferentes níveis de ruído. | Ausência de arquivos de teste em `tests/` relacionados a voz (busca por `test.*voice` retornou 0). |
| **Configuração de VAD exposta apenas em api_keys.json** | Parâmetros como `vad_silencio_ms` e `vad_padding_ms` são ajustáveis apenas por arquivo JSON, não expostos em tempo de execução via API interna, dificultando tuning dinâmico. | [core/gemini_live_voice.py:157-159, 871-880] |

## 3. Bibliotecas recomendadas

| Função | Biblioteca | Justificativa |
|--------|------------|---------------|
| STT offline (fallback) | `faster-whisper` (via `ctranslate2`) | Já utilizada no pipeline de pós‑processamento; fornece transcrição rápida com modelos tiny/base, boa suporte a português e VAD integrado. | [core/gemini_live_voice.py:506-513, requirements.txt:63] |
| Wake word local | `pvporcupine` | Já presente no código, baixa taxa de falsos positivos com palavras‑chave customizadas. | [core/voice_stt.py:154-180, requirements.txt (implícito)] |
| Captura e reprodução de áudio | `sounddevice` (PortAudio) | Usada tanto no modo local quanto no renderer para acesso ao microfone e alto‑falante. | [core/gemini_live_voice.py:806, core/voice_stt.py:235] |
| Detecção de atividade de voz (VAD) | `webrtcvad` ou `silero_vad` (opcional) | Pode substituir o VAD de energia simples por um modelo mais robusto; já referenciado nos scripts de probe. | [scripts/_probe_live_sdk3.py:50] |
| Echo cancellation (software) | `webrtc-audio-processing` (ou rely on Chromium AEC) | Quando `audio_transport` = "local", o AEC do Chromium ainda é eficaz; para cenários totalmente offline, um software AEC pode ser adicionado. | [core/gemini_live_voice.py:265-269 (explicação do modo renderer)] |
| Orquestração de pipeline de voz | `pipecat` (opcional) | Framework baseado em asyncio que já tem suporte a transportes locais, turn‑taking e barge‑in; pode substituir ou complementar a lógica customizada em `gemini_live_voice.py`. | [core/pipecat_voice_pipeline.py:51-52] |

## 4. Configuração de VAD ótima (baseada em melhores práticas observadas)

- **Servidor (Gemini Live)**: usar `silence_duration_ms` entre 300‑500 ms para equilibrar corte precoce e espera excessiva; `prefix_padding_ms` de 100‑150 ms para capturar início da fala; `end_of_speech_sensitivity` = `END_SENSITIVITY_HIGH` para ambientes ruidosos, `LOW` para ambientes silenciosos. Esses valores já são configuráveis via `api_keys.json` (`vad_silencio_ms`, `vad_padding_ms`, `vad_fim_sensivel`). [core/gemini_live_voice.py:157-159, 871-880]
- **Fallback local (se wake word ativado)**: adotar VAD baseado em energia com limiar adaptativo (ex. média móvel do nível de ruído) em vez de valor fixo 0.005; considerar usar `webrtcvad` com modo 3 (mais agressivo) ou `silero_vad` para melhor precisão. [core/voice_stt.py:73, 491]
- **Buffers**: manter buffer deturno de no máximo 2‑3 segundos de áudio (≈ 32000 bytes a 16kHz mono 16‑bit) para evitar atraso excessivo antes da transcrição final. O ZARA já acumula até o silêncio detectado; garantir que o limite máximo de buffer seja imposto para evitar crescimento ilimitado em casos de fala prolongada. [core/gemini_live_voice.py:1330-1334] (atualmente sem limite explícito – gap)
- **Histerese**: ao detectar fim de fala, requerer dois chunks consecutivos abaixo do limiar antes de finalizar, evitando cortes por pausas curtas. Implementável usando contadores de silêncio (similar ao já usado no VoskSTT). [core/voice_stt.py:494-504] (lógica presente)

## 5. Fontes

1. Arquitetura Gemini Live (observada no código): <file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/core/gemini_live_voice.py> (linhas 421-439, 871-880, 1172-1190, 1225-1286, 1330-1334, 1387-1395)  
2. Configuração de wake word e VAD local: <file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/core/voice_stt.py> (linhas 73, 154-180, 491-504)  
3. Uso de faster‑whisper para pós‑processamento: <file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/core/gemini_live_voice.py> (linhas 500-563)  
4. Explicação do modo renderer e AEC do Chromium: <file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/core/gemini_live_voice.py> (linhas 265-269, 421-427)  
5. Documentação de requisitos: <file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/requirements.txt> (linha 63)  
6. Scripts de probe que mencionam webrtcvad e silero_vad: <file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/scripts/_probe_live_sdk3.py> (linha 50)  
7. Pipeline Pipecat local (referência): <file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/core/pipecat_voice_pipeline.py> (linhas 51-52)  

*Todas as afirmações técnicas acima têm URL (caminho interno do projeto) ou são marcadas como [INFERENCIA] quando não há fonte direta. Nenhuma afirmação foi feita sem base.*