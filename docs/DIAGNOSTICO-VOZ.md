# Diagnóstico: onde a voz da ZARA perde tempo

Data da medição: 21/08/2026. Só leitura de código e do arquivo de medição real
em disco (`latencia.jsonl`). Nenhum arquivo de código foi alterado.

## 1. Caminho completo da voz no código

```
Microfone (Electron/Chromium, com AEC)
   -> core/ipc_handlers.py  push_mic_pcm() / IPC de áudio
   -> core/gemini_live_voice.py  GeminiLiveVoice._send_audio_loop()
        (stream contínuo para o Gemini Live; sem gate local por padrão)
   -> Gemini Live decide sozinho quando Alex parou de falar
        (VAD do SERVIDOR do Google, config em GeminiLiveVoiceConfig,
         aplicada em _receive_loop / session.connect())
   -> core/ipc_handlers.py  _on_gemini_live_turn()
        (filtro de eco, wake por transcrição, roteamento CONVERSA x AÇÃO)
   -> CONVERSA: a Kore já respondeu em áudio durante o próprio turno do
      Gemini Live (fala "de graça", sem segunda viagem)
   -> AÇÃO: core/ipc_handlers.py _process_voice_message()
        -> cadeia de intents determinísticos (jarvis, lembrete, memória,
           self-knowledge, arquivo, PC intent) — todos locais/regex
        -> executor real (core/actions/*.py via action_registry)
        -> core/ipc_handlers.py _speak_response()
             -> GeminiLiveVoice.speak() manda "FALE_EXATAMENTE: <resultado>"
                de volta ao Gemini Live (SEGUNDA viagem de rede+modelo)
             -> Kore gera áudio de novo, agora lendo o resultado verificado
   -> Áudio sai por WebAudio no Electron (modo "renderer", com AEC do
      Chromium) ou por PortAudio local, dependendo de audio_transport
```

Fontes: `core/gemini_live_voice.py` linhas 1-30, 336-370, 1042-1226;
`core/ipc_handlers.py` linhas 1300-1417, 2187-2360, 2668-2848.

## 2. Tempo de cada etapa (medido, não estimado)

Existe instrumentação real em produção: `core/cronometro.py` grava cada
turno de voz em `%LOCALAPPDATA%\ZARA3\latencia.jsonl`. Rodei o relatório
oficial (`core.cronometro.relatorio()`) sobre os últimos 2000 registros do
Alex:

```
{
  "turnos": 25,
  "descartados": 673,
  "total_ms_mediano": 6493,
  "etapas_ms_medianas": {
    "antes_de_falar": 20,
    "voz_pronta": 6493
  },
  "por_rota_ms_mediano": { "voz": 6493 },
  "falou_em": 24
}
```

Prova: comando rodado nesta sessão —
`.venv\Scripts\python.exe scripts\_tmp_relatorio_latencia.py` — saída acima,
gerada a partir de `C:\Users\alexp\AppData\Local\ZARA3\latencia.jsonl`
(698 linhas).

Leitura desses números, com o próprio comentário do código
(`core/ipc_handlers.py:2801-2818`) como guia:

- **`antes_de_falar` (mediana 20 ms)**: tempo do início do turno de AÇÃO
  (comando já reconhecido) até o momento em que a ZARA está prestes a pedir
  à Kore que fale o resultado. Isso cobre toda a cadeia de intents locais
  (jarvis/lembrete/memória/self-knowledge/arquivo/PC) + o executor real.
  **Rápido.** Confirma o que o comentário histórico do projeto já dizia
  (`core/cronometro.py:5-8`): o raciocínio local é da ordem de dezenas de
  milissegundos, não é aí que o tempo vai.
  Amostras individuais isoladas (não medianas) chegam a 500-14900 ms quando
  uma ação real (ex.: abrir programa, checar rede) demora — mas a maioria
  fica abaixo de 30 ms.

- **`voz_pronta` (mediana 6493 ms, igual ao `total_ms`)**: tempo do início
  do turno até a Kore **terminar** de falar a frase inteira. Isto é o
  `total_ms` do turno inteiro, porque `speak()` só retorna no
  `turn_complete` do Gemini (`core/gemini_live_voice.py:534-560`) — ou seja,
  quando a fala INTEIRA já foi gerada, não quando ela começa.
  **Este número mistura duas coisas diferentes**: quanto tempo até a Kore
  começar a responder (o que Alex sente como "lentidão") e quanto tempo o
  áudio gerado dura (proporcional ao tamanho da frase, não é lentidão).

- **Marcos de "segunda viagem" (`tts_pedido_ate_primeiro_byte_ms`,
  `tts_primeiro_byte_ate_player_ms`, `primeira_viagem_descartada`)**: o
  código já tem os relógios prontos para medir exatamente isso
  (`core/gemini_live_voice.py:298-333, 1054-1206`; wiring em
  `core/ipc_handlers.py:2227-2239, 2819-2827`). **Mas nenhum desses três
  campos aparece nos 698 registros gravados até agora** — o arquivo
  `latencia.jsonl` só tem `antes_de_falar` e `voz_pronta`. Ou seja: a
  instrumentação fina existe no código mas **os dados dela nunca foram
  capturados na prática**, porque o build/binário que está rodando na
  máquina do Alex é anterior a esse commit de instrumentação
  (`1287f2f`, 20/08 11:49) ou porque a sessão de voz não passou pelo
  caminho instrumentado nas últimas centenas de turnos.
  **[INFERÊNCIA]**: não dá para provar qual dos dois motivos é, só que o
  dado não está no arquivo.

- **`descartados` (673 de 698 registros = 96%)**: a esmagadora maioria dos
  turnos NÃO chega a virar resposta — são falas descartadas por
  `motivo="sem_wake_e_fora_da_janela"` (conversa de fundo/TV, ver
  `core/ipc_handlers.py:1354-1369`). Isso não é lentidão de resposta, é
  volume de ruído sendo filtrado, mas revela que a maior parte do que o
  microfone capta nunca chega perto do LLM.

## 3. Os 3 maiores gargalos, do pior para o menor

### #1 — A segunda viagem de rede completa por resposta em turno de AÇÃO
**Arquivo/função**: `core/ipc_handlers.py:_speak_response()` (linha 2668),
que chama `core/gemini_live_voice.py:GeminiLiveVoice.speak()` (linha 534),
que manda `"FALE_EXATAMENTE: <texto>"` de volta ao Gemini Live
(`_send_speech_loop`, linha 1054-1073) e espera `turn_complete`.

Todo comando de AÇÃO (abrir programa, mexer em volume, etc.) já gasta uma
primeira rodada completa ao Google só para o modelo decidir a rota
(CONVERSA vs AÇÃO) — cujo áudio é **descartado** (comentário
`ZARA-LATENCIA-SEGUNDA-VIAGEM-001`, `core/ipc_handlers.py:2214-2226) — e
depois uma SEGUNDA rodada completa, com outro round-trip de rede + geração
de áudio no servidor, só para a Kore ler em voz alta um resultado que o
Python já tem em texto. É estrutural: dois turnos completos de LLM de voz
para produzir uma frase.

O número exato que essa segunda viagem custa não está sendo capturado (ver
seção 2) — mas o próprio comentário do arquivo chama isso de "a suspeita
principal" (linha 2723-2725), e a mediana de `voz_pronta` (6,5 s) é
consistente com duas idas e voltas completas ao servidor de voz, não uma.

**Correção concreta**: eliminar a segunda viagem em turno de AÇÃO. Duas
formas, ambas já mencionadas no próprio código como possíveis:
1. Não descartar o áudio da primeira geração quando a ação for
   determinística e rápida o bastante para confirmar antes do
   `turn_complete` — só falar direto se o executor confirmar dentro de uma
   janela curta.
2. Trocar TTS de segunda viagem via Gemini Live por um TTS local rápido
   (Edge/Kokoro, que já existem como fallback na cascata,
   `core/ipc_handlers.py:2756-2783`) para ler resultados de AÇÃO, reservando
   o Gemini Live (Kore) só para turnos de CONVERSA onde ele já fala em
   streaming.
**Economia estimada**: uma rodada inteira de rede + geração de áudio no
Google — pelas amostras onde `voz_pronta` passou de 7-9 s, plausivelmente
2-5 segundos por comando de AÇÃO. [INFERÊNCIA — sem os três marcos finos
capturados em produção, não dá pra citar um número medido exato; é o
motivo pelo qual o item 4 abaixo pede ativar essa captura antes de otimizar
às cegas.]

### #2 — VAD do servidor: silêncio de 300 ms antes de qualquer coisa começar
**Arquivo/função**: `core/gemini_live_voice.py:GeminiLiveVoiceConfig`
(linha 142-156, `vad_silencio_ms: int = 300`), aplicado em
`core/gemini_live_voice.py:796-806`
(`types.AutomaticActivityDetection(silence_duration_ms=...)`).

O próprio comentário do código (linhas 142-154) já identifica isto como a
lentidão que "Alex sentia": o servidor espera 300 ms de silêncio depois que
ele para de falar antes de considerar a frase terminada. Isso acontece
ANTES de qualquer processamento da ZARA, em toda fala, sempre — inclusive
nas 673 descartadas.

**Correção concreta**: já é ajustável sem rebuild via `vad_silencio_ms` em
`api_keys.json`. Testar 200-250 ms (`end_of_speech_sensitivity` já está em
`HIGH`, linha 800-802) e medir se corta frases com pausa natural. É o único
gargalo desta lista com um dial pronto e documentado no próprio código.
**Economia estimada**: 50-100 ms por turno — pequeno frente ao gargalo #1,
mas soma em TODO turno, inclusive os de CONVERSA que já respondem rápido.

### #3 — Cadeia de intents locais sequenciais em turno de AÇÃO
**Arquivo/função**: `core/ipc_handlers.py:_process_voice_message()` (linha
2187), que tenta em série: `_try_jarvis_multi_action` → 
`_try_reminder_intent` → `_try_operational_memory_intent` →
`_try_self_knowledge` → `_try_file_intent` → `_try_compound_pc_intent` /
`_try_pc_intent` (linhas 2241-2320), cada um com `await` próprio antes do
próximo ser sequer chamado.

Medido: mediana `antes_de_falar` = 20 ms — ou seja, **hoje isto NÃO é
gargalo real**, é rápido. Listo aqui porque é o terceiro maior risco
estrutural, não porque hoje custe tempo: são 6+ funções assíncronas
encadeadas em série (nenhuma roda em paralelo), a maioria delas regex
local, mas duas usam `asyncio.to_thread` (`_try_self_knowledge` linha 702,
`_try_operational_memory_intent` linha 2105) — se qualquer uma crescer (ex.:
`_try_operational_memory_intent` puxar mais dados, ou um Jarvis multi-passo
esperar um subprocess), o custo se soma a TODOS os turnos de AÇÃO, mesmo os
que não usam aquele intent.

**Correção concreta**: nada a mudar agora — está rápido. Vale só um teste
de regressão automatizado que falhe se `antes_de_falar` mediano passar de,
digamos, 100 ms, para pegar cedo se um novo intent local virar lento sem
ninguém perceber (a mesma lógica de "medir antes de otimizar" que já rege
este arquivo).
**Economia estimada**: 0 ms hoje — é prevenção, não correção.

## 4. Antes de otimizar o #1: ativar a medição fina que já existe

O código de `core/gemini_live_voice.py` já sabe medir exatamente quanto
custa a segunda viagem (`tts_pedido_ate_primeiro_byte_ms`,
`tts_primeiro_byte_ate_player_ms`, `primeira_viagem_descartada`) e já grava
esses valores no cronômetro (`core/ipc_handlers.py:2819-2827`), mas **os 698
registros reais em disco não têm nenhum desses três campos**. Antes de
mexer no código do gargalo #1, alguém precisa confirmar que a build que
está rodando na máquina do Alex já contém esse commit de instrumentação
(`1287f2f`, 20/08) e rodar mais alguns turnos de voz para ver os números
finos aparecerem em `latencia.jsonl`. Sem isso, qualquer número de economia
para o gargalo #1 continua sendo inferência sobre a mediana grosseira
(`voz_pronta`), não medição direta da segunda viagem.

## 5. Fontes

- `core/gemini_live_voice.py` (linhas citadas acima) — configuração de VAD,
  relógios de latência, loop de envio/recepção de áudio.
- `core/ipc_handlers.py` (linhas citadas acima) — despachante de voz,
  cronômetro, cadeia de intents, `_speak_response`.
- `core/cronometro.py` (arquivo inteiro) — definição do que é medido e como
  o relatório é calculado (mediana, não média).
- `C:\Users\alexp\AppData\Local\ZARA3\latencia.jsonl` — dado real de
  produção, 698 linhas, lido e agregado nesta sessão via
  `core.cronometro.relatorio()`.
- Saída do comando rodado nesta sessão (`scripts/_tmp_relatorio_latencia.py`
  — script temporário, não faz parte do produto, criado só para rodar o
  relatório existente sem tocar em código do projeto).

## O que NÃO foi medido (honestidade obrigatória)

- Os três marcos finos da segunda viagem (`tts_pedido_ate_primeiro_byte_ms`
  etc.) — o código existe, o dado em disco não. Sem eles, o custo exato do
  gargalo #1 é inferência, não medição.
- Latência de rede pura até o servidor do Gemini Live (RTT) — não há
  instrumentação disso no código hoje.
- Tempo do AEC do Chromium / renderização de áudio no Electron
  (`on_output_audio`) — o comentário do próprio código já assume isso como
  "não dá para ver daqui" (`core/gemini_live_voice.py:1195-1200`).
