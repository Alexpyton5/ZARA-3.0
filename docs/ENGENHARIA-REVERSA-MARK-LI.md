# Engenharia Reversa do Mark-LI — Padrões de Plugin System, Memory, Actions, UI

**Data:** 2026-08-22  
**Autor:** @pesquisador_reverso  
**Projeto alvo:** ZARA 3.0  
**Fonte primária:** https://github.com/FatihMakes/Mark-LI (commit 363a3bd, 20/08/2026)

---

## 1. Arquitetura Recomendada

### 1.1 Núcleo: Plugin System "Drop-in" (Arquitetura Final)

O Mark-LI adota um **plugin system auto-descoberto** como unidade atômica de extensão. Cada habilidade é **um único arquivo `.py`** em `plugins/` — sem registro manual, sem configuração, sem tocar no core.

**Características-chave (extraídas de `core/plugin_loader.py`):**
- Descoberta determinística: `sorted(plugins_dir.glob("*.py"))`, ignora arquivos começando com `_` (`__init__.py`, `_template.py`)
- Import isolado via `importlib.util.spec_from_file_location` — falha de um plugin **nunca** derruba os outros
- Validação em 3 camadas:
  1. **Estrutura:** `PLUGIN` dict obrigatório com `name` (snake_case, regex `^[a-zA-Z_][a-zA-Z0-9_]{0,63}$`), `description` (string não-vazia), `parameters` (dict com `"type": "OBJECT"`)
  2. **Assinatura:** `run(parameters: dict, player=None, session_memory=None) -> str` — inspeção via `inspect.signature` aceita `**kwargs` ou parâmetros nomeados
  3. **Colisão:** rejeita nomes que batem com *core tools* ou com outros plugins já carregados
- **Crash isolation:** Exceções em `run()` são capturadas, logadas, e retornam string de erro falada — o loop principal continua
- **Hot-toggle:** Estado enabled/disabled lido de `config/api_keys.json` (`plugins_enabled.{name}`) a cada chamada — **não requer restart**
- **UI integrada:** `list_for_ui()` expõe `{name, description, file, valid, error, enabled}` para o Plugin Manager no HUD

**Template oficial (`plugins/_template.py`):**
```python
PLUGIN = {
    "name": "my_plugin",
    "description": "Gatilho explícito + qual tool NÃO usar se houver ambiguidade",
    "parameters": {"type": "OBJECT", "properties": {...}, "required": []},
}
def run(parameters, player=None, session_memory=None) -> str:
    # Nunca raise; capture e retorne string de erro falada
```

### 1.2 Memória: Estrutura em Camadas com TTL e Trim Automático

`memory/memory_manager.py` implementa **memória persistente em JSON único** (`memory/long_term.json`) com:

- **6 categorias fixas:** `identity`, `preferences`, `projects`, `relationships`, `wishes`, `notes` — cada entrada = `{value, updated: "YYYY-MM-DD"}`
- **Trim por tamanho:** `MEMORY_MAX_CHARS = 2200` — quando `json.dumps()` excede, remove entradas mais antigas (ordenadas por `updated`) até caber
- **Truncamento de valor:** `MAX_VALUE_LENGTH = 380` caracteres por entry
- **Thread-safe:** `threading.Lock` em todas as operações de escrita
- **Session memory consumível:** `sessions[]` (máx 3) — `pop_last_session()` **remove** a entrada após ler, garantindo que briefing matinal nunca repita
- **Formatação para prompt:** `format_memory_for_prompt()` injeta cabeçalho `[WHAT YOU KNOW...]` + seções limitadas (identity 8 campos, prefs 15, projects 8, relationships 10, wishes 8, notes 8), teto 2000 chars

### 1.3 Actions: Ferramentas de Core como Funções Síncronas Puras

Todas as actions em `actions/*.py` seguem o padrão:
```python
def action_name(parameters: dict, player=None, response=None, speak=None, session_memory=None) -> str:
    # player: instância JarvisUI para write_log()
    # response: legado, hoje None
    # speak: callback para fala assíncrona mid-task (code_helper, dev_agent, game_updater)
    # Retorna string natural falada ao usuário
```
- **Nenhuma action é async** — o dispatcher em `main.py` roda via `loop.run_in_executor(None, lambda: action(...))`
- **Validação de parâmetros** feita pelo Gemini via schema declarada em `TOOL_DECLARATIONS` (main.py)
- **Erro = string falada** — nunca raise; loga no player e retorna mensagem de erro

### 1.4 Voice Pipeline: Gemini Live API nativo com VAD Server-Side

`main.py` (JarvisLive) + `core/stt.py` + `core/tts.py` mostram:

- **STT primário:** Gemini Live **nativo** (`input_audio_transcription` + `output_audio_transcription`) — sem Whisper/Vosk no caminho principal
- **VAD 100% server-side:** Configurado via `AutomaticActivityDetection`:
  - `silence_duration_ms` (padrão 300ms) — quando o servidor fecha o turno
  - `prefix_padding_ms` (100ms) — preserva início da fala
  - `end_of_speech_sensitivity: HIGH` — fecha mais rápido
- **Context window compression:** `SlidingWindow()` — sessão **nunca morre** por context window cheio
- **Session resumption:** `SessionResumptionConfig(handle=...)` — reconexão transparente
- **Affective dialog + Proactive audio:** `enable_affective_dialog=True`, `proactive_audio=True` — Gemini ouve emoção e silencia quando fala não é para ele
- **Voice:** Charon (hardcoded no LiveConnectConfig)

### 1.5 UI: PyQt6 HUD com Plugin Manager Integrado

`ui.py` — Janela frameless, always-on-top, 3 painéis (esquerdo: métricas/log; central: waveform + status; direito: content panel + plugin manager):
- **Plugin Manager overlay:** lista todos os plugins (válidos + inválidos) com toggle ON/OFF persistido em config
- **Dynamic theming:** `apply_ui_accent(hex)` — shift de hue preservando saturação/luminosidade, aplica a HUD, waveform, métricas
- **Camera stream:** QLabel com QTimer 30fps para webcam visão
- **Content panel:** scrollable area beneath HUD renderiza resultados de web_search, file_processor, etc.
- **Remote dashboard:** FastAPI + uvicorn + QR code para controle via celular

### 1.6 Proactive Engine 2.0 (Context-Aware, Non-Repetitive)

`actions/proactive.py` — Decide **QUANDO** falar e constrói prompt rico:
- **Gates:** `min_silence_secs=900` (15 min usuário silencioso) + `check_cooldown=1200` (20 min entre proativas)
- **Rotação de foco** (`_rotation % 3`): projetos → bem-estar/time-of-day → fato curioso/útil
- **Contexto injetado:** memória formatada + monitores ativos + últimos 6 turns da conversa atual
- **Regra de ouro:** "Se nada genuinamente útil vier à mente, fique em silêncio"

---

## 2. Gaps da ZARA Hoje (vs. Mark-LI)

| Capacidade | Mark-LI | ZARA 3.0 | Gap |
|------------|---------|----------|-----|
| **Plugin system drop-in** | ✅ `plugins/*.py` auto-descoberto, crash-isolado, hot-toggle, UI manager | ❌ Actions hardcoded em `core/actions/*.py`, sem isolamento, sem UI | **Arquitetural** — ZARA precisa migrar para plugin loader equivalente |
| **Memória estruturada + trim + session consumível** | ✅ 6 categorias, trim 2200 chars, `pop_last_session()` | ⚠️ `core/aprendizado.py` existe mas sem trim, sem session consumível, sem formatação p/ prompt | **Funcional** — memory_manager do Mark-LI é superior |
| **VAD server-side configurável** | ✅ `silence_duration_ms`, `prefix_padding_ms`, `END_SENSITIVITY_HIGH` | ⚠️ `vad_silencio_ms=300` em `gemini_live_voice.py` mas **sem** `prefix_padding_ms` nem `end_sensitivity` | **Latência** — ZARA não controla padding nem sensibilidade de fim |
| **Context window compression (sliding window)** | ✅ `SlidingWindow()` nativo | ❌ Não configurado em `gemini_live_voice.py` | **Sessões longas** — ZARA vai truncar/quebrar em conversas > 1h |
| **Session resumption** | ✅ `SessionResumptionConfig(handle=...)` | ❌ Não implementado | **Robustez** — Reconexão perde contexto |
| **Affective dialog + Proactive audio** | ✅ Nativo no Live API | ❌ Não habilitado | **Qualidade** — ZARA não ouve emoção nem silencia em background chatter |
| **Proactive check-ins context-aware** | ✅ Engine 2.0 com rotação, monitores, sessão recente | ❌ Não existe | **Proatividade** — ZARA só reage |
| **Plugin Manager UI** | ✅ Overlay com toggles persistidos | ❌ Não existe | **UX** — Alex não liga/desliga skills |
| **Remote dashboard (QR + phone)** | ✅ FastAPI + cryptography | ❌ Não existe | **Controle remoto** |
| **Dynamic theming (hue shift)** | ✅ `apply_ui_accent()` | ❌ Cores hardcoded | **Personalização** |
| **Vision cooldown (4s)** | ✅ `_vision_last_time` + `_vision_busy` | ❌ Não existe | **Anti-spam** de screen_process |
| **OS-native reminders (Task Scheduler/LaunchAgent/systemd)** | ✅ `actions/reminder.py` | ⚠️ Existe mas sem verificação cross-platform | **Confiabilidade** |
| **Hardware monitoring contínuo + alertas de voz** | ✅ `SystemMonitor` (CPU/RAM/GPU/temp) | ❌ Não existe | **Telemetria** |
| **Morning briefing com pop_last_session** | ✅ Consome sessão, nunca repete | ❌ Não existe | **Rotina matinal** |
| **Background topic monitoring (DDG daily)** | ✅ `background_monitor.py` | ❌ Não existe | **Alertas de tópicos** |

---

## 3. Libs Recomendadas (para fechar gaps)

| Gap | Lib / Componente | Justificativa | Fonte no Mark-LI |
|-----|------------------|---------------|------------------|
| Plugin system | `importlib.util` (stdlib) + padrão `PluginRegistry` | Zero dep, isolamento total, hot-reload via config | `core/plugin_loader.py` |
| Memória com trim/TTL | Implementar `MemoryManager` baseado no Mark-LI | JSON único, thread-safe, trim por tamanho, session consumível | `memory/memory_manager.py` |
| VAD server-side completo | `google.genai.types.AutomaticActivityDetection` | Já disponível no SDK; só expor `prefix_padding_ms` e `end_sensitivity` | `main.py:796-806` |
| Context compression | `types.ContextWindowCompressionConfig(sliding_window=types.SlidingWindow())` | Nativo no Live API; evita morte de sessão | `main.py:784-786` |
| Session resumption | `types.SessionResumptionConfig(handle=...)` | Reconexão transparente; salva `session_resumption_update.new_handle` | `main.py:787-789, 1081-1085` |
| Affective dialog / Proactive audio | `enable_affective_dialog=True`, `proactivity=ProactivityConfig(proactive_audio=True)` | Nativo no Live API; melhora percepção de "presença" | `main.py:749-750` |
| Proactive engine | Portar `ProactiveEngine` (puro Python, sem deps extras) | Context-aware, non-repetitive, rotação de foco | `actions/proactive.py` |
| UI Plugin Manager | PyQt6 `QScrollArea` + toggles persistidos em config | Já existe `ui.py` base; adicionar overlay | `ui.py` (Plugin Manager section) |
| Remote dashboard | `fastapi`, `uvicorn[standard]`, `cryptography`, `qrcode` | QR pairing, controle via celular | `ui.py` (RemoteDashboard class) |
| Dynamic theming | `colorsys` (stdlib) — hue shift preservando S/L | Aplica a toda paleta turquesa-family | `ui.py:apply_ui_accent()` |
| Vision cooldown | Timestamp + flag `_vision_busy` + cooldown 4s | Evita spam de screen_process | `main.py:806-813` |
| OS-native reminders | `win32com.client` (Task Scheduler), `launchd` (macOS), `systemd` (Linux) | Notificações nativas, persistem após reboot | `actions/reminder.py` |
| Hardware monitoring | `psutil` + `GPUtil` (opcional) + thresholds de voz | Telemetria contínua, alertas falados | `actions/system_monitor.py` |
| Background monitoring | `duckduckgo-search` (DDG HTML scrape) daily + persist topics | Zero API key, roda 1x/dia | `actions/background_monitor.py` |
| Morning briefing | `pop_last_session()` + news fetch + weather + memory | Consome sessão, nunca repete | `main.py` (briefing logic) + `actions/web_search.py` |

---

## 4. Config de VAD Ótima (para ZARA)

Baseada no Mark-LI (`main.py:796-806`) + ajustes medidos na ZARA (`gemini_live_voice.py:142-156`, `latencia.jsonl` mediana `total_ms=6493`):

```python
# Em GeminiLiveVoiceConfig (gemini_live_voice.py) — expor em api_keys.json:
vad_silencio_ms: int = 300        # Atual: 300. Mark-LI usa 300. OK.
vad_padding_ms: int = 100         # NOVO: preserva 100ms antes do VAD fechar (evita cortar "que horas")
vad_fim_sensivel: bool = True     # Atual: True. Mark-LI usa HIGH. OK.

# LiveConnectConfig (em _build_config ou _run):
realtime_input_config=types.RealtimeInputConfig(
    automatic_activity_detection=types.AutomaticActivityDetection(
        silence_duration_ms=300,        # vad_silencio_ms
        prefix_padding_ms=100,          # vad_padding_ms (NOVO)
        end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_HIGH
    )
)

# Context window compression (NOVO — evita sessão morrer):
context_window_compression=types.ContextWindowCompressionConfig(
    sliding_window=types.SlidingWindow()
)

# Session resumption (NOVO — reconexão transparente):
session_resumption=types.SessionResumptionConfig(
    handle=self._session_handle  # salvo em session_resumption_update
)

# Affective dialog + Proactive audio (NOVO — qualidade):
enable_affective_dialog=True,
proactivity=types.ProactivityConfig(proactive_audio=True)
```

**Por que `prefix_padding_ms=100` importa:** Sem ele, o VAD do servidor pode cortar o primeiro fonema ("q" de "que horas") — relatado como "audição ruim" pelo Alex. O padding garante que o buffer enviado ao modelo inclua o lead-in.

**Por que `SlidingWindow()` importa:** Hoje a ZARA não configura — a sessão Live usa o padrão (sem compressão). Em conversas > 1h o context window enche e a sessão derruba. `SlidingWindow()` mantém a conversa viva indefinidamente.

---

## 5. Fontes (URL por Afirmação)

| Afirmação | URL |
|-----------|-----|
| Plugin system drop-in, descoberta, validação, crash isolation, hot-toggle, UI list_for_ui | https://raw.githubusercontent.com/FatihMakes/Mark-LI/main/core/plugin_loader.py |
| Template oficial de plugin (`PLUGIN` dict + `run()`) | https://raw.githubusercontent.com/FatihMakes/Mark-LI/main/plugins/_template.py |
| Estrutura de memória: 6 categorias, trim 2200 chars, truncamento 380, session consumível, formatação p/ prompt | https://raw.githubusercontent.com/FatihMakes/Mark-LI/main/memory/memory_manager.py |
| Config manager: `plugins_enabled`, `assistant_name`, `user_name`, `morning_brief_enabled` | https://raw.githubusercontent.com/FatihMakes/Mark-LI/main/memory/config_manager.py |
| Actions pattern: funções síncronas, `player` para log, `speak` callback, retorno string falada | https://raw.githubusercontent.com/FatihMakes/Mark-LI/main/actions/open_app.py |
| TOOL_DECLARATIONS completas (26 core tools) + plugin registry merge | https://raw.githubusercontent.com/FatihMakes/Mark-LI/main/main.py (linhas 1-550) |
| JarvisLive: LiveConnectConfig, VAD config, SlidingWindow, SessionResumption, affective dialog, proactive audio | https://raw.githubusercontent.com/FatihMakes/Mark-LI/main/main.py (linhas 684-814) |
| ProactiveEngine 2.0: gates, rotação, contexto, regra de silêncio | https://raw.githubusercontent.com/FatihMakes/Mark-LI/main/actions/proactive.py |
| UI: PyQt6 HUD, Plugin Manager overlay, dynamic theming, camera stream, content panel, remote dashboard | https://raw.githubusercontent.com/FatihMakes/Mark-LI/main/ui.py |
| STT engines: Whisper (faster-whisper, VAD-buffered) + Vosk (streaming) | https://raw.githubusercontent.com/FatihMakes/Mark-LI/main/core/stt.py |
| TTS engines: EdgeTTS (free), Kokoro (offline), ElevenLabs (cloud) | https://raw.githubusercontent.com/FatihMakes/Mark-LI/main/core/tts.py |
| LLM client local: Ollama + OpenAI-compatible, tool calling, streaming sentences | https://raw.githubusercontent.com/FatihMakes/Mark-LI/main/core/llm_client.py |
| Vision cooldown 4s + `_vision_busy` flag | https://raw.githubusercontent.com/FatihMakes/Mark-LI/main/main.py (linhas 806-835) |
| OS-native reminders (Task Scheduler/LaunchAgent/systemd) | https://raw.githubusercontent.com/FatihMakes/Mark-LI/main/actions/reminder.py |
| Hardware monitoring (CPU/RAM/GPU/temp) + alertas de voz | https://raw.githubusercontent.com/FatihMakes/Mark-LI/main/actions/system_monitor.py |
| Background topic monitoring (DDG daily) | https://raw.githubusercontent.com/FatihMakes/Mark-LI/main/actions/background_monitor.py |
| Morning briefing com `pop_last_session` | https://raw.githubusercontent.com/FatihMakes/Mark-LI/main/main.py (briefing logic) + https://raw.githubusercontent.com/FatihMakes/Mark-LI/main/actions/web_search.py |
| Web search multi-mode (search/news/research/price/compare) com Gemini Grounded | https://raw.githubusercontent.com/FatihMakes/Mark-LI/main/actions/web_search.py |
| Repo root (estrutura de pastas, roadmap, capabilities) | https://github.com/FatihMakes/Mark-LI |

---

## Notas de Inferência

- **[INFERENCIA]** O Mark-LI não expõe `prefix_padding_ms` nem `end_sensitivity` via config file — estão hardcoded no `LiveConnectConfig`. A recomendação para ZARA expô-los em `api_keys.json` é baseada no padrão existente de `vad_silencio_ms`.
- **[INFERENCIA]** `SlidingWindow()` e `SessionResumptionConfig` não aparecem no README — foram extraídos do código vivo em `main.py`. Funcionam no preview API mas podem mudar.
- **[INFERENCIA]** `enable_affective_dialog` e `proactive_audio` são flags do preview Gemini Live; o Mark-LI as ativa e tem fallback gracioso (`_enhanced_live` auto-desabilita se servidor rejeitar). ZARA deve replicar o padrão de fallback.

---

## Próximos Passos Executáveis (para @executor_dev)

1. **Criar `core/plugin_loader.py`** baseado no Mark-LI — mover `core/actions/*.py` para `plugins/` como plugins válidos
2. **Substituir `core/aprendizado.py`** por `memory/memory_manager.py` + `memory/config_manager.py` (trim, session consumível, formatação)
3. **Adicionar em `GeminiLiveVoiceConfig`**: `vad_padding_ms`, `vad_fim_sensivel` (já existe), expor no `api_keys.json`
4. **No `_run()` do `GeminiLiveVoice`**: adicionar `context_window_compression`, `session_resumption`, `enable_affective_dialog`, `proactive_audio`
5. **Portar `ProactiveEngine`** para `actions/proactive.py` e integrar no loop principal
6. **Adicionar Plugin Manager overlay** no `frontend/src` (PyQt6 → React/Electron equivalente)
7. **Implementar vision cooldown** (4s) no handler de `screen_process`
8. **Adicionar remote dashboard** (FastAPI + QR) se prioritário

---

**FIM DO DOCUMENTO**