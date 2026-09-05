# ZARA 3.0 — BASELINE AUDIT 001
**Data**: 2026-08-22  
**Ambiente**: Windows 11, Python 3.11 (venv), Projeto real em `C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002`  
**Objetivo**: Fatos verificados do pipeline de voz, registro de ações, capability gate, memória, roteador de modelos e hardware/RAM. **Nenhuma funcionalidade alterada.**

---

## 1. HARDWARE E RECURSOS

| Componente | Especificação | Fonte |
|---|---|---|
| **RAM Total** | 16.9 GB (16.944.734.208 bytes) | `wmic computersystem get TotalPhysicalMemory` |
| **CPU** | Intel Core i5-10500H @ 2.50 GHz, 12 logical processors | `wmic cpu get Name,NumberOfLogicalProcessors` |
| **GPU 1** | Intel UHD Graphics — 1 GB VRAM | `wmic path win32_videocontroller get Name,AdapterRAM` |
| **GPU 2** | NVIDIA GeForce GTX 1650 — 4.3 GB VRAM | `wmic path win32_videocontroller get Name,AdapterRAM` |
| **SO** | Windows 11 | Host info |
| **Python** | 3.11.15 (venv `.venv`) | `pyproject.toml:requires-python = ">=3.11"` |

> **Nota**: RAM ~17 GB permite rodar modelos locais (Ollama qwen3:4b ~2.5 GB) sem pressão de memória, mas não comporta modelos maiores (ex: 70B quantizados). GPU GTX 1650 (4 GB) não roda inferência LLM local com desempenho útil; serve apenas para aceleração de vídeo/OCR.

---

## 2. PIPELINE DE VOZ (GEMINI LIVE)

### 2.1 Arquitetura e Transporte
- **Motor**: Gemini 3.1 Flash Live Preview (WebSocket `wss://generativelanguage.googleapis.com/v1beta`)
- **Voz**: Kore (feminina, PT-BR nativa)
- **Transporte de áudio**: Dois modos, reversíveis sem rebuild via `api_keys.json`:
  - `audio_transport: "local"` — PortAudio (microfone + alto-falante direto no Python). **Sem AEC**; eco próprio volta pelo microfone.
  - `audio_transport: "renderer"` (padrão no EXE) — Electron renderer captura microfone e toca via WebAudio; **AEC do Chromium** cancela eco da Kore. Requer que a fala saia pelo mesmo processo que captura.
- **Wake word**: **OFF por padrão** (`wake_word_enabled: False`). O microfone transmite continuamente; o wake é decidido por **transcrição** em `ipc_handlers._on_gemini_live_turn` (`_WAKE_PREFIX_RE`). Modo legado (Vosk local) volta com `"wake_word_mode": "local"`.
- **VAD do servidor**: `vad_silencio_ms=300`, `vad_padding_ms=100`, `vad_fim_sensivel=HIGH` (END_SENSITIVITY_HIGH). Medido como ótimo — não mexer sem A/B test.

### 2.2 Latência Medida (Fonte: `docs/LATENCIA-VOZ.md`, dados de `%LOCALAPPDATA%\ZARA3\latencia.jsonl` — 715 linhas, 40 turnos válidos)

| Métrica | Valor | Status vs. Alvo (< 500 ms) |
|---|---|---|
| **Latência total mediana** (fim da fala → voz audível) | **4.130 ms** | ❌ 8,3× alvo |
| **Gargalo #1: Primeira viagem descartada** | **6.702 ms** | ❌ 13,4× alvo |
| **Gargalo #2: TTS pedido → primeiro byte (Kore)** | **1.082 ms** | ❌ 2,2× alvo |
| **Antes de falar (decisão + executor)** | **20 ms** | ✅ Dentro |
| **Primeiro byte → player (entrega local)** | **1 ms** | ✅ Dentro |

**Conclusão**: O "pensamento" (LLM + executor = 20 ms) **não é o problema**. O tempo que Alex sente (4–7 s) vem de **duas viagens de rede ao Google Live em série**, e a primeira é **jogada fora** em turnos de ação.

### 2.3 Por Que a Primeira Viagem Existe
Em `core/gemini_live_voice.py:1130-1176`:
1. Alex fala → VAD do servidor fecha turno
2. Gemini Live **gera resposta completa em áudio** (Kore falando)
3. No `_receive_loop`, o código detecta `model_turn` com áudio
4. Como `self._turn_direct == False` (turno de AÇÃO), o `if audio_data and (self._play_generated_audio or self._turn_direct)` dá **False**
5. **Todo o áudio gerado é descartado byte a byte**
6. Só depois o executor roda e faz a segunda viagem (`FALE_EXATAMENTE:`)

Turnos de **conversa (DIRECT)** tocam streaming direto (~300–500 ms percebido). Turnos de **ação (EXECUTOR)** pagam o custo da primeira viagem descartada + segunda viagem TTS (~7.800 ms total).

### 2.4 Otimizações Já Implementadas (Evidência no Código)
1. VAD configurado (300/100/HIGH) — `gemini_live_voice.py:142-156, 796-806`
2. Wake word local DESLIGADO (evita 1,2 s buffer + corte) — `gemini_live_voice.py:156-176`
3. Conversa direta (turno DIRECT toca streaming) — `gemini_live_voice.py:1132-1146`
4. Cooldown assíncrono (não bloqueia receive_loop) — `gemini_live_voice.py:599-621`
5. Medição em disco (Cronometro + latencia.jsonl) — `core/cronometro.py`, `ipc_handlers.py:2161-2192`

---

## 3. REGISTRO DE AÇÕES (ACTION REGISTRY)

### 3.1 Total e Distribuição
- **106 ações registradas** (auto-registradas via `@action` decorator no import de `core/actions/__init__.py`)
- **Categorias**: `system` (8), `os` (28), `browser` (10), `media` (13), `files` (11), `code` (6), `scheduler` (6), `vision` (4), `web` (4), `os` (demais)

### 3.2 Níveis de Risco e Capability Gates
| Risco | Ações | Exige Confirmação | Capability Mínima |
|---|---|---|---|
| **LOW** (72) | Não | Não | `READ_ONLY` ou `LOCAL_PC_CONTROL` |
| **MEDIUM** (20) | Sim (`confirm=true` ou política) | Sim | `PC_CONTROL`, `FILES_MUTATE`, `CODE_EXECUTION` |
| **HIGH** (14) | Sim (challenge IPC dedicado) | Sempre | `SYSTEM_POWER`, `CODE_EXECUTION`, `FILES_MUTATE` |

**Capability Gate** (`core/action_registry.py:260-284`):
- `pc_control_allowed = False` por padrão (Supercérebro OFF)
- Ações com capability `PC_CONTROL`, `REMOTE_PC_CONTROL`, `AGENTIC_PC_CONTROL`, `FILES_MUTATE`, `CODE_EXECUTION`, `SYSTEM_POWER` **são bloqueadas** se `pc_control_allowed == False`
- Ações `READ_ONLY` e `LOCAL_PC_CONTROL` **sempre permitidas** (volume, brilho, janelas, media, clipboard read, etc.)

### 3.3 Ações Fundamentais (Carregadas no Boot)
53 ações em `core/capability_registry.py:FUNDAMENTAL_ACTIONS` — system info, audio, media, volume/brightness, clipboard, window básico, web search/fetch, files read-only. O resto é **lazy-loaded** via `load_capability(action_name)`.

### 3.4 Campo `verificado` no ActionResult
- `verificado: bool = True` — **True** = houve pós-condição observada (releitura, estado do Windows)
- **False** = despachou e não deu para conferir. **Não é falha: é incerteza**, e aparece como incerteza para Alex (`ActionResult.incerto`).
- Regra: **nunca declarar sucesso sem checar `result.success` e `result.verificado`**.

---

## 4. CAPABILITY GATE (CAPABILITY REGISTRY)

- **Arquivo**: `core/capability_registry.py`
- **Mecanismo**: Mapeia `action_name → module_name` lendo `core/actions/__init__.py` (AST). `load_capability(action_name)` faz `importlib.import_module('core.actions.' + module_name)` sob demanda.
- **Fundamentais** (53): Sempre carregados em `load_fundamentals()`.
- **Não fundamentais**: Carregados na primeira chamada via `ensure_loaded()` (usado pelo dispatcher antes de executar).
- **Fallback**: Se módulo não encontrado no mapeamento, retorna `False` (ação "desconhecida").

---

## 5. SISTEMAS DE MEMÓRIA

### 5.1 Memória Semântica de Longo Prazo (`memory/memory_manager.py`)
- **Arquivo**: `%LOCALAPPDATA%\ZARA3\memory\long_term.json` (120 bytes atual)
- **Categorias**: `identity`, `preferences`, `projects`, `relationships`, `wishes`, `notes`
- **Limite**: 2.200 chars totais (trim automático por LRU em `save_memory()`)
- **Proteção**: Filtro de segredos (API keys, tokens, passwords) — `_SENSITIVE_MEMORY_PATTERNS` bloqueia escrita
- **Exportação**: `export_memory()` redige sensíveis como `[redigido por privacidade]`
- **Sessões**: `_SESSION_MAX = 3` resumos curtos em `memory['sessions']`

### 5.2 Memória Episódica Vetorizada (`memory/episodic_memory.py`)
- **Arquivo**: `%LOCALAPPDATA%\ZARA3\memory\zara_episodes.sqlite3` (397 KB)
- **Schema**: `episodes(id, created_at, kind, content, metadata, vector BLOB)`
- **Embeddings**: `nomic-embed-text` via Ollama (local, HTTP `localhost:11434/api/embeddings`)
- **Busca**: Cosseno + overlap léxico (peso 0.35), top-k padrão 3, max 700 chars no contexto
- **WAL mode** SQLite para concorrência

### 5.3 Aprendizado Diário (`core/aprendizado.py`)
- **Arquivo**: `%LOCALAPPDATA%\ZARA3\data\aprendizado\experiencias.db` (479 KB)
- **Tabelas**: `episodios` (pedido, forma, ação, sucesso, resultado, reação) + `licoes` (forma, ação, acertos, erros, exemplo)
- **Ciclo**: `registrar_acao()` → espera reação (janela 90s) → `observar_reacao()` detecta reclamação/elogio → atualiza `licoes`
- **Forma do pedido**: Normalização sem acento + tokens úteis (ex: "abaixa o volume" ≈ "diminui volume" → mesma chave)
- **Diário**: `fechar_o_dia()` automático na virada do dia (`fechar_o_dia_se_preciso()`), guarda acertos/erros em tabela `diario`
- **Absorção do projeto**: `absorver_do_projeto(texto, fonte)` extrai decisões/resultados de conversas com Claude/Codex (marcadores: "consertei", "está pronto", "não funciona")

---

## 6. ROTEADOR DE MODELOS (MODEL ROUTER)

### 6.1 Registro de Modelos (`core/model_router.py:MODEL_REGISTRY`)
**20 modelos configurados** divididos por provedor:

| Provedor | Modelos | Grátis/Zero-Cost | Auto-Eligible | Observação |
|---|---|---|---|---|
| **NVIDIA NIM** | Nemotron 3 Ultra 550B, DeepSeek V4 Pro, Nemotron 3 Super 120B, GLM-5.2 | Sim (endpoint free/trial) | Sim | Tools ✓, prioridade 1-2 |
| **Groq** | GPT-OSS 120B, GPT-OSS 20B | Sim (free plan limits) | Sim | Tools ✓, rate limits conhecidos |
| **Gemini** | 3.6 Flash, 3.5 Flash-Lite, 2.5 Pro, 2.5 Flash | Sim (free tier) | Sim | Tools ✓ |
| **Z.AI** | GLM-4.7 Flash | Provider limits | Sim (priority 4) | Sem key hoje → dorme |
| **xAI** | Grok 4.5 | **PAGO** | **Não** | `zero_cost_eligible=False`, `auto_eligible=False` |
| **Anthropic** | Opus 5, Sonnet 5, Haiku 4.5 | **CREDIT_COOLDOWN** | Sim (mas breaker aberto) | Circuit breaker: 402 abre, probe 200 fecha auto |
| **Ollama Local** | Qwen3 4B | **Local/Zero cost** | Sim | `base_url=http://localhost:11434/v1` |
| **Hermes Gateway** | Supercérebro | Local | **Não** | `auto_eligible=False`, só com `include_hermes=True` |
| **Gemini Live** | Kore (voz) | N/A | Não | `task_type=VOICE` apenas, WebSocket |

### 6.2 Políticas de Roteamento
- **smart** (padrão): quality/task-fit first, zero-cost eligible only
- **economy**: fast/light/free-quota preserving first
- **manual**: escolha explícita respeitada; **nenhum fallback silencioso**

### 6.3 Health Tracking
- Por **provider** e por **model** (`provider_health`, `model_health`)
- Estados: `AVAILABLE`, `LIMITED`, `COOLDOWN`, `EXHAUSTED`, `AUTH_INVALID`, `ERROR`
- Auto-recovery: cooldown expira → `AVAILABLE`
- Anthropic inicia em `CREDIT_COOLDOWN` (6h window); probe 200 reabre automaticamente

### 6.4 Classificação de Intenção
- Regex por `TaskType` (CODING, REASONING, GENERAL_CHAT, CREATIVE, QUICK_FACTS, VOICE, LOCAL_PRIVATE, TOOL_USE, DECISION)
- Contexto injeta prioridade: `voice_mode` → VOICE, `require_tools` → TOOL_USE, `private_mode` → LOCAL_PRIVATE

---

## 7. CONFIGURAÇÃO ATIVA (`%LOCALAPPDATA%\ZARA3\config\api_keys.json`)

```json
{
  "gemini_api_key": "«redacted»",
  "groq_api_key": "«redacted»",
  "nvidia_api_key": "«redacted»",
  "hermes_ativo": false,
  "hermes_url": "http://127.0.0.1:8642",
  "hermes_api_key": "«redacted»",
  "wake_word_mode": true,          // NOTE: código default é False; este valor ativa gate Vosk local
  "voice_mode": "gemini_live",
  "gemini_live_model": "gemini-3.1-flash-live-preview",
  "gemini_live_voice": "Kore",
  "ai_engine": "auto_smart"
}
```

> **Discrepância**: `wake_word_mode: true` no JSON, mas `GeminiLiveVoiceConfig.wake_word_enabled = False` no código. Se o JSON for lido e aplicado, o gate Vosk local **liga** (1,2 s buffer, corte de comando, sem barge-in). Verificar se `ipc_handlers` lê e aplica essa config.

---

## 8. DEPENDÊNCIAS PRINCIPAIS (`pyproject.toml`)

| Pacote | Versão Mínima | Uso |
|---|---|---|
| `httpx` | 0.27.0 | HTTP cliente assíncrono |
| `google-genai` | 2.13.0 | Gemini Live API |
| `pydantic` | 2.8.0 | Validação/config |
| `vosk` | 0.3.45 | STT offline (wake gate legado) |
| `pvporcupine` | 3.0.0 | Wake word porcupine (não usado no modo padrão) |
| `kokoro-onnx` | 0.3.0 | TTS local fallback |
| `sounddevice` | 0.4.6 | Áudio PortAudio (modo local) |
| `pycaw` | 20240210 | Volume Windows (Core Audio) |
| `psutil` | 5.9.0 | Métricas sistema |
| `playwright` | 1.40.0 | Browser automation |
| `opencv-python` | 4.8.0 | Visão computacional |
| `pillow` | 10.0.0 | Imagens |
| `numpy` | 1.24.0 | Numérico |
| `scipy` | 1.10.0 | Científico |

**Dev**: `pytest`, `pytest-asyncio`, `ruff`, `mypy`, `pyinstaller`

---

## 9. ESTRUTURA DE DADOS (RUNTIME)

```
%LOCALAPPDATA%\ZARA3\
├── config/
│   └── api_keys.json                 # Chaves e flags de runtime
├── data/
│   ├── aprendizado/experiencias.db   # Aprendizado diário (479 KB)
│   ├── conversation_history.sqlite3  # Histórico conversas (315 KB)
│   ├── autonomy/                     # Engine de autonomia
│   ├── brain/                        # Estado do "cérebro"
│   ├── lab/                          # Laboratório de agentes
│   ├── mentor-relay/                 # Bridge Mentor (Issue #5)
│   ├── project-memory/               # Contexto projeto (mentor_context_latest.md)
│   ├── reminders/                    # Lembretes persistentes
│   └── user_memory/                  # Memória de usuário
├── memory/
│   ├── long_term.json                # Memória semântica (120 B)
│   └── zara_episodes.sqlite3         # Memória episódica (397 KB)
├── models/                           # Modelos Vosk/Whisper/Ollama
├── corujao/                          # Modo noturno (kanban+watchdog)
├── latencia.jsonl                    # Métricas voz (134 KB, 715 linhas)
├── model_catalog_snapshot.json       # Catálogo Ollama/HF
├── model_usage_stats.json            # Stats uso modelos
└── provider_health_diagnostic.json   # Saúde provedores
```

---

## 10. PONTOS DE ATENÇÃO (NÃO CORRIGIDOS NESTA AUDITORIA)

1. **Wake word mode conflitante**: JSON diz `true`, código default `False`. Se aplicado, reativa gate Vosk com regressão conhecida (corte de comando, sem barge-in).
2. **Primeira viagem descartada (6.7 s)**: Gargalo #1 identificado, sem fix ainda. Opções documentadas em `LATENCIA-VOZ.md` (Opção A/B/C).
3. **Telegram Grupo**: `core/telegram_grupo.py` **não existe no source** (apenas em backups `.orig*`). EXE atual (build 17/ago) **não tem** a ponte; MD5 idêntico ao anterior → build fake.
4. **Anthropic em CREDIT_COOLDOWN**: Circuit breaker aberto; modelos não entram no roteamento até probe 200.
5. **Ollama local**: Requer serviço rodando em `localhost:11434`; não verificado ativo.
6. **Hermes Gateway**: `hermes_ativo: false`; Supercérebro desligado por padrão.
7. **Single-writer lock**: Advisory only (warn, não bloqueia). Dois processos ZARA no mesmo data dir corrompem SQLite/WAL.

---

## 11. ARQUIVOS DE REFERÊNCIA PRINCIPAIS

| Arquivo | Função |
|---|---|
| `docs/LATENCIA-VOZ.md` | Medição real pipeline voz (40 turnos, 715 linhas) |
| `core/gemini_live_voice.py` | Pipeline Gemini Live nativo (69 KB, 1.471 linhas) |
| `core/action_registry.py` | Registry 106 ações + gates risco/capability (23 KB) |
| `core/capability_registry.py` | Lazy loading capacidades (3.9 KB) |
| `core/model_router.py` | Roteador smart/economy/manual + health (32 KB) |
| `core/aprendizado.py` | Aprendizado diário + diário automático (17 KB) |
| `memory/memory_manager.py` | Memória semântica longo prazo (17 KB) |
| `memory/episodic_memory.py` | Memória episódica vetorizada (7.6 KB) |
| `core/ipc_handlers.py` | Despachante central voz/texto (221 KB) |
| `core/pc_voice_intent.py` | Detector intenções PC por voz (48 KB) |
| `core/trust_gate.py` | Validação skills externas (9 KB) |
| `core/paths.py` | Resolução paths (LOCALAPPDATA vs source) |

---

## 12. COMANDOS DE VERIFICAÇÃO RÁPIDA

```bash
# Hardware
wmic computersystem get TotalPhysicalMemory
wmic cpu get Name,NumberOfLogicalProcessors
wmic path win32_videocontroller get Name,AdapterRAM

# Ações registradas
cd "C:/Users/alexp/Downloads/ZARA 3.0 CLEAN 002"
.venv/Scripts/python.exe scripts/list_actions2.py

# Latência (últimas 10 linhas)
tail -10 %LOCALAPPDATA%\ZARA3\latencia.jsonl

# Config ativa
type %LOCALAPPDATA%\ZARA3\config\api_keys.json

# Testes
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check core memory integrations tests --output-format=concise
```

---

**Fim do baseline.** Este documento reflete **estado verificado em 2026-08-22**, sem alterações de funcionalidade. Qualquer mudança futura deve atualizar este documento ou criar versão 002.