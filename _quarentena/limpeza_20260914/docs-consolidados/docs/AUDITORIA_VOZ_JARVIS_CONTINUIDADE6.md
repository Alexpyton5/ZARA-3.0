# Auditoria de Voz Estilo JARVIS – ZARA 3.0 (Continuidade 6)

## 1. Arquitetura Recomendada (JARVIS‑style)

| Componente | Estado atual na ZARA | Recomendação (JARVIS) | Fonte |
|------------|----------------------|-----------------------|-------|
| **Transporte de áudio** | Pode ser `local` (PortAudio) ou `renderer` (Electron/Chromium AEC). O modo `renderer` é o único que fornece cancelamento de eco real porque o áudio de saída e entrada compartilham o mesmo processo. | Manter `audio_transport: renderer` como padrão obrigatório para garantir AEC do Chromium e permitir barge‑in sem auto‑eco. | file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/core/gemini_live_voice.py#l135-141 |
| **Wake word** | Gate Vosk local desligado por padrão (`wake_word_enabled: false`). Wake detectado por transcrição no servidor (`_WAKE_PREFIX_RE` em `ipc_handlers`). | Manter wake word baseado apenas em transcrição do servidor (sem gate local) para evitar corte de início de frase e permitir barge‑in durante a fala da assistente. | file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/core/gemini_live_voice.py#l6-27; file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/core/ipc_handlers.py#l31-43 |
| **VAD (Voice Activity Detection)** | Usa o VAD nativo do servidor Gemini Live, configurável via `vad_silencio_ms` (padrão 300 ms) e `vad_padding_ms` (100 ms) em `api_keys.json`. Não há VAD local de pré‑filtro. | Manter VAD servidor como fonte de verdade para turn‑taking; adicionar um VAD local leve (ex. WebRTC VAD) apenas para melhorar detecção de início de fala e reduzir falsos positivos de eco, mantendo o servidor como árbitro final. | file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/core/gemini_live_voice.py#l142-156; file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/tests/test_voice_latency_vad.py |
| **Barge‑in (interrupção)** | Possível porque o microfone está sempre aberto para o Gemini (gate local desligado). O servidor vê a interrupção e corta a geração de áudio. O eco próprio é filtrado por conteúdo (`looks_like_assistant_echo`). | Preservar fluxo contínuo de mic → servidor; melhorar o filtro de eco com limiar adaptativo baseado na energia do áudio de saída medido no renderer. | file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/core/gemini_live_voice.py#l19-24; file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/tests/test_voice_barge_in.py |
| **Cancelamento de eco** | Quando `audio_transport = renderer`, o Chromium fornece AEC. Além disso, há filtro de conteúdo (`_looks_like_assistant_echo`) que bloqueia transcrições que parecem eco da própria resposta. | Manter AEC do renderer como primeira linha de defesa; manter filtro de conteúdo como segunda linha para casos de atraso variável. Não é necessário gate local de áudio. | file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/core/gemini_live_voice.py#l22-24; file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/core/gemini_live_voice.py#l74-122 |
| **Turn‑taking e fluidez** | O agente responde em turnos curtos (1‑2 frases) por instrução de sistema (`system_instruction`). Não há métrica explícita de latência de primeira fala no código; a medição é feita somente após `speak()` voltar (término da fala). | Exibir métricas de *time‑to‑first‑audio* (TFA) e *time‑to‑turn‑complete* em logs ou telemetria; garantir que o VAD servidor não aguarde silêncio excessivo antes de processar a fala do usuário. | file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/core/gemini_live_voice.py#l187-238 |
| **Recuperação de conexão** | Não há lógica explícita de reconexão automática após queda do WebSocket do Gemini Live. O objeto `GeminiLiveVoice` para e aguarda reinicialização externa. | Implementar reconexão exponencial com back‑off e notificação de estado (`state: RECONNECTING`) ao frontend. | [INFERENCIA] – ausência de tratamento de `_session_handle` após erro |

## 2. Gaps da ZARA Hoje (relacionados ao estilo JARVIS)

| Gap | Evidência / Impacto | Fonte |
|-----|---------------------|-------|
| **Latência de primeira fala não medida internamente** | O cronômetro existente inicia somente após o turno do usuário fechar no servidor (`_t_fim_fala_usuario`) e é lido depois de `speak()` voltar (término da fala). Não há marca do primeiro byte de áudio de saída chegando ao renderer. | file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/core/gemini_live_voice.py#l299-315; comentários no código indicam que a medição atual é de “quanto demora até ela TERMINAR de falar”. [INFERENCIA] |
| **Ausência de fallback local de STT/TTS** | Se o Gemini Live ficar indisponível, a voz cai para silêncio (nenhum áudio). Não há pipeline local de STT/TTS configurado como backup. | file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/tests/test_voice_usability.py (resposta `SEM_VOZ_DISPONIVEL`) |
| **Nenhuma indicação visual de estado de escuta** | O frontend não recebe um sinal distinto de `LISTENING` vs `PROCESSING` vs `SPEAKING` além do nível de áudio genérico. O usuário não sabe se a ZARA está ouvindo ou pensando. | file:///C:/alexp/Downloads/ZARA%203.0%20CLEAN%20002/core/ipc_handlers.py (campos `speaking`, `level`; nenhum campo específico para `gate_open` ou `vad_active`). [INFERENCIA] |
| **Tuning de VAD exposto apenas via `api_keys.json`** | Ajustar `vad_silencio_ms` requer edição manual de JSON e reinício; não há interface de runtime para experimentar valores. | file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/core/gemini_live_voice.py#l152-156 |
| **Filtrado de eco baseado exclusivamente em conteúdo** | O filtro `looks_like_assistant_echo` pode falhar quando o eco está muito atrasado ou ruidoso, pois depende de sobreposição de tokens. Não há verificação de energia ou atraso de áudio. | file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/core/gemini_live_voice.py#l74-122 |
| **Não há detecção proativa de interrupção por voz** | O barge‑in depende do VAD do servidor detectar silêncio; se o usuário falar sobre a fala da ZARA sem pausar suficientemente, o servidor pode não considerar o turno encerrado. | file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/tests/test_voice_barge_in.py (testa apenas interrupções claras) [INFERENCIA] |
| **Ausência de métricas de confiabilidade de wake word** | O wake word baseado em transcrição pode gerar falsos positivos (gatilho por fala semelhante) ou falsos negativos (falha ao reconhecer em ruído). Não há registro de taxa de acerto ou latência de detecção. | file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/core/ipc_handlers.py#l31-43 [_WAKE_PREFIX_RE] [INFERENCIA] |

## 3. Libs Recomendadas (para suprir gaps)

| Função | Biblioteca | Por quê | URL/Fonte |
|--------|------------|---------|-----------|
| VAD local leve (pré‑filtro) | `webrtcvad` (ou `silero-vad` via torch) | Baixo consumo, bom para detecção de início de fala antes de enviar ao servidor. | https://pypi.org/project/webrtcvad/ |
| Medição de latência de áudio em tempo real | `sounddevice` + `numpy` | Captura timestamp do primeiro bloco de áudio de saída do renderer para calcular TFA. | https://pypi.org/project/sounddevice/ |
| Detecção de energia de áudio (para filtro de eco adaptativo) | `numpy` (RMS) ou `librosa` | Permite ajustar limiar de filtro de eco com base na energia real do sinal de saída. | https://pypi.org/package/numpy |
| Reconexão exponencial com back‑off | `tenacity` ou implementação custom | Simplifica lógica de reconexão do WebSocket do Gemini Live. | https://pypi.org/project/tenacity/ |
| Métricas de telemetria (Prometheus‑like) | `prometheus-client` | Exportar contadores de turnos, latências, erros de VAD, etc. | https://pypi.org/project/prometheus-client/ |

## 4. Config de VAD Ótima (baseada em evidência interna)

| Parâmetro | Valor atual (padrão) | Faixa segura observada | Comentário |
|-----------|----------------------|------------------------|------------|
| `vad_silencio_ms` | `300` | `150 – 400` ms (teste `test_voice_latency_vad.py` passou com 50‑150 ms e 400 ms) | Valor de 300 ms é o ponto de equilíbrio medido internamente; valores abaixo de 150 ms podem cortar pausas naturais; acima de 400 ms aumentam latência percebida. | file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/core/gemini_live_voice.py#l152-156; file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/docs/RECOMENDACOES-VOZ.md#l74-78 |
| `vad_padding_ms` | `100` | `50 – 150` ms | Padding adequado para evitar corte de fonemas finais; não afeta significativamente a latência. | file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/core/gemini_live_voice.py#l154 |
| `vad_fim_sensivel` | `True` | Manter `True` | Sensibilidade alta ajuda a detectar fim de fala mais cedo, reduzindo latência artificial. | file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/core/gemini_live_voice.py#l155 |
| **Sugestão de ajuste fino** | `vad_silencio_ms = 200` | `180 – 250` ms | Reduz espera de silêncio sem aumentar risco de corte, conforme indicado nos comentários do código (“300 ms é o equilíbrio medido, mas testes com valores menores podem reduzir a latência total…”). | file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/docs/RECOMENDACOES-VOZ.md#l74-78 |

## 5. Fontes (URL de cada afirmação)

- Arquitetura e fluxo de áudio: `core/gemini_live_voice.py` (linhas 6‑27, 135‑141, 19‑24, 74‑122) → file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/core/gemini_live_voice.py
- Wake word via transcrição: `core/ipc_handlers.py` (linhas 31‑43) → file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/core/ipc_handlers.py
- VAD configurável: `core/gemini_live_voice.py` (linhas 142‑156) → file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/core/gemini_live_voice.py
- Testes de barge‑in: `tests/test_voice_barge_in.py` → file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/tests/test_voice_barge_in.py
- Testes de latência VAD: `tests/test_voice_latency_vad.py` → file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/tests/test_voice_latency_vad.py
- Comentário sobre equilíbrio de 300 ms: `docs/RECOMENDACOES-VOZ.md` linhas 74‑78 → file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/docs/RECOMENDACOES-VOZ.md
- System instruction de turnos curtos: `core/gemini_live_voice.py` linhas 187‑238 → file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/core/gemini_live_voice.py
- Falta de métricas de primeira fala: análise do código (`gemini_live_voice.py:299‑315`) e ausência de logs de TFA → [INFERENCIA]
- Ausência de fallback/local STT: observado nos testes `test_voice_usability.py` (resultado `SEM_VOZ_DISPONIVEL`) → file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/tests/test_voice_usability.py
- Nenhuma indicação visual de estado: inspeção de `ipc_handlers.py` (campos `speaking`, `level` sem equivalente de `gate_open`) → [INFERENCIA]
- Filtro de eco baseado em conteúdo: `core/gemini_live_voice.py` linhas 74‑122 → file:///C:/Users/alexp/Downloads/ZARA%203.0%20CLEAN%20002/core/gemini_live_voice.py
- Nenhum tratamento de reconexão explícito: inspeção de `GeminiLiveVoice` (não há método de reconexão automática) → [INFERENCIA]

---

*Este documento está pronto para ser utilizado como base de melhoria da arquitetura de voz da ZARA rumo ao estilo JARVIS.*