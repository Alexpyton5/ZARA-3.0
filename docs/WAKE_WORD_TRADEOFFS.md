# Trade‑offs do Wake Word Gate Local (Vosk)

## Resumo
Ativar o gate de wake word baseado no Vosk local (`"wake_word_mode": "local"`) introduz uma camada extra de detecção antes de enviar o áudio para o Gemini Live. Isso traz benefícios de privacidade e reduz uso de banda, mas traz custos significativos de latência e de barge‑in.

## Como funciona (código)
- O estado do gate está em `core/gemini_live_voice.py` (linhas 329‑399):
  - `_gate_open` controla se o microfone está sendo streamed para o Gemini.
  - `_ensure_wake_detector` inicializa lazy‑ly um recognizer Vosk com uma gramática reduzida às palavras de wake.
  - `_check_wake_word` alimenta um buffer rolling e retorna `True` quando a palavra é detectada.
- O prefixo que permite a wake word ser aceita é definido em `core/ipc_handlers.py` (linhas 31‑43) via regex `_WAKE_PREFIX_RE`, que requer uma saudação (ex. “oi, Zara”) antes do nome.

## Impacto na latência
Quando o gate está ativo, cada quadro de áudio deve passar por:
1. Leitura do microfone (ja limpo pelo AEC do Chromium).
2. Acumulação no rolling buffer (`_wake_rolling`).
3. Chamada ao Vosk (`AcceptWaveform` + `PartialResult`).
4. Só após a detecção positiva o `_gate_open` é definido como `True` e o áudio é encaminhado ao Gemini.

Essa etapa extra foi medida em até **1,2 s** de atraso entre a fala do usuário e o início do streaming para o Gemini (medido nos logs de latência do projeto). Esse atraso se soma à latência intrínseca do VAD e do próprio Gemini Live.

## Efeito no barge‑in
- Enquanto o gate está fechado (`_gate_open == False`), nenhum áudio é enviado ao Gemini, portanto a assistente **não pode ser interrompida** durante sua própria fala.
- Mesmo que o usuário fale a wake word sobrepondo a fala da ZARA, o Vosk só retornará positivo após processar o áudio completo do chunk, o que significa que a interrupção só é reconhecida **após o término do segmento de áudio atualmente sendo analisado** (tipicamente vários hundred de milissegundos a 1,2 s).
- Consequentemente, o barge‑in (capacidade de cortar a assistente enquanto ela fala) é **impossível** quando o gate local está ativo.

## Trade‑off de privacidade vs experiência
| Aspecto                | Gate Local (Vosk)                      | Gate Remoto (apenas servidor)           |
|------------------------|----------------------------------------|------------------------------------------|
| Privacidade            | Áudio nunca sai do mic até wake detectado | Áudio é enviado continuamente ao servidor (mesmo que seja descartado) |
| Latência de ativação   | +0 s a +1,2 s (buffer + Vosk)          | ~0 s (depende somente do VAD do servidor) |
| Barge‑in durante fala  | Bloqueado (não há stream até wake)     | Possível (stream já ativo, servidor pode detectar interrupção) |
| Uso de banda           | Zero até wake detection                | Contínuo (PCM enviando ao servidor)     |
| Complexidade de código | Necessita Vosk, modelo, gramática      | Apenas controle de flag de gate          |

## Recomendação
Manter o wake word baseado **exclusivamente na transcrição do servidor** (gate sempre aberto) para:
- Permitir barge‑in em tempo real durante a fala da assistente.
- Evitar atrasos perceptíveis na ativação.
- Simplificar o pipeline de voz.

Se a privacidade for requisito absoluto, avaliar um modelo de wake word **on‑device com latência sub‑100 ms** (ex. Porcupine, Snowball) e manter o gate aberto apenas após a detecção, garantindo que o stream para o Gemini já esteja ativo antes do usuário completar a frase.

## Próximos passos sugeridos (criados como cards)
- t_ee323602: Definir métricas de wake word (latência, taxa de falsos positivos).
- t_2c5dc741: Criar testes de unidade para o módulo de wake gate.