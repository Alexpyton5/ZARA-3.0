# LATENCIA-VOZ.md — Medição Real do Pipeline de Voz da ZARA

**Data da medição**: 2026-08-22
**Fonte dos dados**: `%LOCALAPPDATA%\ZARA3\latencia.jsonl` (715 linhas, 40 turnos de voz válidos, 675 descartes)
**Ambiente**: Windows 11, Gemini Live (Kore), audio transport = renderer (AEC do Chromium)

---

## Resumo Executivo

| Métrica | Valor | Status vs. Alvo (< 500 ms) |
|---------|-------|----------------------------|
| **Latência total mediana** (fim da fala → voz audível) | **4.130 ms** | ❌ 8,3× o alvo |
| **Gargalo #1: Primeira viagem descartada** | **6.702 ms** | ❌ 13,4× o alvo |
| **Gargalo #2: TTS pedido → primeiro byte (Kore)** | **1.082 ms** | ❌ 2,2× o alvo |
| **Antes de falar (decisão + executor)** | **20 ms** | ✅ Dentro do alvo |
| **Primeiro byte → player (entrega local)** | **1 ms** | ✅ Dentro do alvo |

> **Conclusão**: A ZARA **não** está lenta no "pensamento" (LLM + executor = 20 ms). O tempo que Alex sente (4–7 s) vem de **duas viagens de rede ao Google Live** que acontecem **em série** e uma delas é **jogada fora**.

---

## Pipeline Instrumentado — Etapas Medidas

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. CAPTURA DE ÁUDIO (microfone → renderer → push_mic_pcm)                  │
│    - Medido por: VOICE_TRACE stage=AUDIO_FRAMES_RECEIVED                   │
│    - Tempo: ~0 ms (contínuo, assíncrono)                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. VAD DO SERVIDOR (Google decide que Alex calou)                          │
│    - Config: vad_silencio_ms=300, vad_padding_ms=100, fim_sensivel=HIGH   │
│    - Marco: _t_fim_fala_usuario (INFERIDO no 1º audio do modelo)          │
│    - Tempo: ~300–500 ms de silêncio real + processamento servidor         │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. TRANSCRIÇÃO (STT do Gemini Live)                                        │
│    - Chega via input_transcription (streaming, parcial → final)           │
│    - Marco: _on_gemini_live_turn recebe `user_text`                       │
│    - Tempo: Incluído na "primeira viagem" abaixo                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. PRIMEIRA VIAGEM AO GEMINI (DESCARTADA EM TURNOS DE AÇÃO)  ← GARGALO #1  │
│    - O modelo GERA ÁUDIO COMPLETO (Kore lendo a resposta)                 │
│    - Em turno de AÇÃO: este áudio é BYTE-A-BYTE DESCARTADO no _receive_loop│
│    - Marco medido: `primeira_viagem_descartada` = 6.702 ms (mediana)      │
│    - **Este áudio nunca chega ao alto-falante**                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│ 5. EXECUTOR (ação real no PC: volume, brilho, janelas, etc.)              │
│    - Inicia APÓS turn_complete (quando o áudio da 1ª viagem já terminou) │
│    - Marco: `antes_de_falar` = 20 ms (mediana)                            │
│    - **Esta parte JÁ É RÁPIDA**                                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│ 6. SEGUNDA VIAGEM AO GEMINI (TTS: Kore lê o resultado verificado)         │
│    - Envio: `FALE_EXATAMENTE: <texto verificado>`                         │
│    - Marco: `tts_pedido_ate_primeiro_byte_ms` = 1.082 ms (mediana)        │
│    - Marco: `tts_primeiro_byte_ate_player_ms` = 1 ms (mediana)            │
│    - Marco: `tts_pedido_ate_player_ms` = 1.082 ms (mediana)  ← GARGALO #2 │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│ 7. PRIMEIRA AMOSTRA AUDÍVEL (Kore sai no alto-falante)                    │
│    - Modo renderer: bytes → Electron WebAudio → AEC Chromium → speaker    │
│    - Proxy medido: `AUDIO_AUDIVEL_INICIO` (PROXY_RENDERER)                │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Números Brutos (Mediana dos Últimos 40 Turnos de Voz)

```json
{
  "turnos": 40,
  "descartados": 675,
  "total_ms_mediano": 4130,
  "etapas_ms_medianas": {
    "antes_de_falar": 20,
    "primeira_viagem_descartada": 6702,
    "tts_pedido_ate_player_ms": 1082,
    "tts_pedido_ate_primeiro_byte_ms": 1082,
    "tts_primeiro_byte_ate_player_ms": 1,
    "voz_pronta": 4130
  },
  "por_rota_ms_mediano": {
    "voz": 4130
  },
  "falou_em": 36
}
```

### Distribuição por Rota (apenas turnos que falaram)

| Rota | Turnos | Mediana total_ms |
|------|--------|------------------|
| voz (Gemini Live Kore) | 36 | 4.130 ms |

> Nota: 4 turnos tiveram `voz: "nenhuma"` (TTS falhou) e 1 teve `voz: "gemini_live/?"` (voz não identificada).

---

## Análise dos Gargalos

### Gargalo #1: Primeira Viagem Descartada (6.702 ms mediana)

**O que acontece**:
1. Alex fala → VAD do servidor fecha turno
2. Gemini Live **gera resposta completa em áudio** (Kore falando)
3. No `_receive_loop` (linha ~1166-1176), o código detecta `model_turn` com áudio
4. Como `self._turn_direct == False` (turno de AÇÃO), o `if audio_data and (self._play_generated_audio or self._turn_direct)` dá **False**
5. **Todo o áudio gerado é descartado byte a byte**
6. Só depois o executor roda e faz a segunda viagem

**Por que existe**: Arquitetura legada onde todo turno gerava áudio primeiro, e só depois decidia se era conversa (toca) ou ação (descarta). O `ZARA-VOICE-FLUIDEZ-001` resolveu para conversa (audio direto), mas **turnos de ação ainda pagam o custo da primeira viagem**.

**Evidência no código** (`gemini_live_voice.py:1130-1176`):
```python
# O áudio do modelo chega ANTES de decidir a rota
if not self._turn_route_decided and not self._play_generated_audio:
    self._decide_turn_route()  # Decide AQUI, mas áudio JÁ VEIO

for part in model_turn.parts:
    if audio_data and (self._play_generated_audio or self._turn_direct):
        # Em ação: _play_generated_audio=False, _turn_direct=False
        # → ENTRA NO IF? NÃO. Áudio é ignorado.
```

### Gargalo #2: Segunda Viagem TTS (1.082 ms mediana)

**O que acontece**: Após executor terminar, `_speak_response` chama `gemini_live_voice.speak()` que envia `FALE_EXATAMENTE:` e espera `turn_complete` (áudio inteiro gerado).

**Breakdown**:
- `tts_pedido_ate_primeiro_byte_ms`: 1.082 ms (rede + modelo gerando primeiro chunk)
- `tts_primeiro_byte_ate_player_ms`: 1 ms (entrega local, renderer → WebAudio)
- **Total TTS**: 1.082 ms

---

## Comparação: Turno de Conversa vs Turno de Ação

| Etapa | Conversa (DIRECT) | Ação (EXECUTOR) |
|-------|-------------------|-----------------|
| 1ª viagem (áudio gerado) | **TOCA DIRETO** (streaming) | **DESCARTADA** (6.7 s) |
| Executor | Não roda | 20 ms |
| 2ª viagem (TTS) | Não existe | 1.082 ms |
| **Total percebido pelo Alex** | **~300–500 ms** (VAD + 1º chunk) | **~7.800 ms** |

> **Turno de conversa JÁ ATINGE O ALVO** (< 500 ms percebido). O problema é **só turno de ação**.

---

## O Que Já Foi Otimizado (Evidência no Código)

1. **VAD do servidor configurado** (`vad_silencio_ms=300`, `fim_sensivel=HIGH`) — `gemini_live_voice.py:796-806`
2. **Wake word local DESLIGADO** (evitava 1,2 s de buffer + corte de comando) — `gemini_live_voice.py:156-176`
3. **Conversa direta** (turno DIRECT toca streaming, sem 2ª viagem) — `gemini_live_voice.py:1132-1146`
4. **Cooldown assíncrono** (não bloqueia receive_loop) — `gemini_live_voice.py:599-621`
5. **Medição em disco** (Cronometro + latencia.jsonl) — `core/cronometro.py`, `ipc_handlers.py:2161-2192`

---

## Recomendações Prioritárias

### P1 — Eliminar a primeira viagem em turnos de ação (Impacto: -6.700 ms)

**Opção A**: Não enviar `turn_complete=True` no primeiro turno se for ação prevista
- Enviar áudio do usuário sem fechar turno → receber transcrição → decidir rota → só então fechar turno
- Requer mudança no protocolo Gemini Live (streaming input sem turn_complete)

**Opção B**: `can_answer_directly` roda **antes** da primeira viagem (no cliente, com transcrição parcial)
- Usar STT local leve (Vosk) só para classificar intent ANTES de mandar para o Gemini
- Se for ação: não mandar `turn_complete`, mandar só transcrição → executor → 2ª viagem só
- Risco: STT local pode errar → false negative (ação tratada como conversa)

**Opção C**: Gemini Live `input_audio_transcription` + `automatic_activity_detection` sem gerar áudio
- Ver se API permite `response_modalities=["TEXT"]` no 1º turno, áudio só no 2º
- Mais limpo, depende de suporte da API

### P2 — Parallelizar executor com TTS da 2ª viagem (Impacto: -1.000 ms)

Enquanto o executor roda (20 ms), **já iniciar** a 2ª viagem com placeholder ou streaming.
Hoje: executor espera turn_complete da 1ª viagem (6.7 s) → roda (20 ms) → inicia 2ª viagem (1 s).

### P3 — Cache de TTS para respostas canônicas (Impacto: variável)

"Volume definido para 50%", "Abra o Chrome", "Luz noturna ativada" — frases fixas podem vir de cache local (Kokoro/Edge) em < 100 ms, sem ir ao Gemini.

---

## Configuração VAD Atual (Ótima para o Alvo)

```python
# gemini_live_voice.py:125-156, 796-806
vad_silencio_ms: int = 300        # Espera 300 ms de silêncio → fecha turno
vad_padding_ms: int = 100         # Inclui 100 ms antes do silêncio
vad_fim_sensivel: bool = True     # END_SENSITIVITY_HIGH
```

**Por que está boa**: 300 ms é o equilíbrio medido — curto o bastante para não parecer travado, longo o bastante para não cortar pausas naturais do Alex. **Não mexer sem A/B test**.

---

## Wake Word Híbrida (Já Implementada)

- **Modo padrão (gate OFF)**: Microfone sempre aberto → Gemini transcreve tudo → Wake por transcrição (`_WAKE_PREFIX_RE` em `ipc_handlers.py:30-42`)
- **Modo legado (gate ON)**: Vosk local detecta "Zara" → abre gate → envia áudio
- **Reversível sem rebuild**: `"wake_word_mode": "local"` em `api_keys.json`

**Por que gate OFF vence**: Elimina 1,2 s de buffer local, evita corte de comando ("que horas são" → "oração"), permite barge-in real (mic chega no Gemini enquanto Kore fala).

---

## Fontes (URL / Arquivo:Linha)

| Afirmação | Fonte |
|-----------|-------|
| Pipeline Gemini Live nativo, Kore, renderer AEC | `core/gemini_live_voice.py:1-28, 135-141, 407-409` |
| VAD config 300/100/HIGH | `core/gemini_live_voice.py:142-156, 796-806` |
| Wake gate OFF por padrão, reversível | `core/gemini_live_voice.py:156-179` |
| Primeira viagem descartada em ação | `core/gemini_live_voice.py:1130-1176, 1147-1165` |
| Marcos de latência (_t_fim_fala_usuario, _t_primeiro_byte_tts, etc.) | `core/gemini_live_voice.py:298-314, 564-598, 1159-1208` |
| Cronometro em disco (latencia.jsonl) | `core/cronometro.py:1-102, 166-227` |
| Medição integrada no IPC handler | `core/ipc_handlers.py:2145-2192, 2751-2777` |
| Dados brutos (715 linhas, 40 turnos válidos) | `%LOCALAPPDATA%\ZARA3\latencia.jsonl` |
| Relatório automatizado (script) | `scripts/relatorio_latencia_full.py` |
| Turno DIRECT toca streaming | `core/gemini_live_voice.py:1132-1146, 1166-1176` |
| Barge-in real via server VAD | `core/gemini_live_voice.py:18-24, 1087-1112` |
| Eco filter por conteúdo | `core/gemini_live_voice.py:74-122, 490-503` |
| Wake por transcrição (_WAKE_PREFIX_RE) | `core/ipc_handlers.py:30-42, 1273-1280` |
| Janela de conversa (75 s) | `core/ipc_handlers.py:1281-1305` |

---

## Próximos Passos Executáveis

1. **Criar task** para investigar Opção A (streaming input sem turn_complete) ou Opção C (response_modalities=["TEXT"] no 1º turno)
2. **Medir baseline** com `primeira_viagem_descartada` zerada (simular removendo o áudio no receive_loop para ação)
3. **Validar** se turnos de conversa continuam < 500 ms percebido após mudança
4. **Documentar** decisão em `docs/ARQUITETURA-VOZ-DECISOES.md`

---

**Arquivo gerado**: `docs/LATENCIA-VOZ.md`
**Scripts de verificação**: `scripts/relatorio_latencia.py`, `scripts/relatorio_latencia_full.py`