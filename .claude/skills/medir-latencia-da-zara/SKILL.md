---
name: medir-latencia-da-zara
description: Mede a latência real da ZARA (fala do Alex → resposta falada) em vez de estimar, usando o SQLite de histórico, os marcadores [VOICE_TRACE] e cronômetro físico, e separa o que foi medido do que foi inferido; use sempre que alguém disser que a ZARA está lenta, ao tentar reduzir latência (Fase 1, prioridade 2) ou antes de declarar que uma mudança deixou a resposta mais rápida.
---

# Medir latência da ZARA

Prioridade 2 da Fase 1. Regra dura: **"ficou mais rápido" sem número é opinião, não resultado.**

## Os quatro trechos de latência (não confundir)

```
T1  fala termina          → STT/Live devolve texto
T2  texto normalizado     → intent casado (determinístico ou LLM)
T3  intent casado         → executor terminou e devolveu postcondição
T4  resposta pronta       → primeiro áudio da Kore sai no alto-falante
```

Otimizar o trecho errado é o loop clássico. **Sempre localizar o trecho antes de mexer.**

## Fontes de medição, da mais barata para a mais cara

### 1. SQLite de conversa — barato, mas granularidade de 1 segundo

Arquivo: `%LOCALAPPDATA%\ZARA3\data\conversation_history.sqlite3`
(caminho vem de `data_dir()` em `core/paths.py`; tabela `conversation_messages`,
colunas `sequence, role, content, engine, created_at`).

`created_at` é epoch **inteiro**. Serve para achar turnos lentos (5 s vs 1 s),
**não** para comparar 900 ms contra 1100 ms.

```sql
SELECT sequence, role, engine, created_at,
       created_at - LAG(created_at) OVER (ORDER BY sequence) AS delta_s
FROM conversation_messages ORDER BY sequence DESC LIMIT 20;
```

Limite honesto: mede o instante em que a mensagem foi **gravada**, não quando o Alex
ouviu a voz. O T4 (síntese + reprodução) fica **fora** dessa conta.

### 2. `[VOICE_TRACE]` — mostra o estágio, mas **não tem timestamp**

Verificado no source: as linhas são `[VOICE_TRACE] stage=... result=...`, sem hora.
Estágios existentes: `IPC_RECEIVE, ROUTE, TURN_ROUTE, AUDIO_TRANSPORT,
AUDIO_FRAMES_RECEIVED, MIC_DEVICE_ENUMERATION, SELECTED_INPUT_DEVICE, MIC_OPEN_RESULT,
KORE_CHECK, LIVE_IMPORT, STT_RESULT, NORMALIZED_TEXT, INTENT_MATCH, ACTION_DISPATCH,
TTS_START, TTS_FALLBACK, REMINDER_TTS, BARGE_IN, TURN_CANCELLED, ECHO_GUARD,
ECHO_SUSPECT, SELF_ECHO, FINAL_RESPONSE`.

Para virar medição, é preciso **carimbar hora na captura**, não no código de produção
primeiro. O sidecar não escreve arquivo de log: `frontend/src/main.ts` só repassa o
stderr para o console do Electron. Então, para ver trace no build empacotado, abra o EXE
**por um console** e capture com hora:

```powershell
& "<caminho do EXE>" 2>&1 | ForEach-Object { "{0:HH:mm:ss.fff} {1}" -f (Get-Date), $_ } | Tee-Object -FilePath "$env:TEMP\zara-trace.txt"
```

Se for preciso instrumentar o source, o menor delta é acrescentar `t=<perf_counter>` às
linhas `[VOICE_TRACE]` já existentes — **sem** mudar roteamento, sem mudar intent.
Isso é uma tarefa própria, com seu próprio build.

### 3. Cronômetro físico — o único número que o Alex sente

Alex fala, cronômetro no celular, para quando ouve o primeiro som da Kore.
3 repetições da mesma frase, anotar as 3. É `PHYSICAL_BY_ALEX` / `VOICE_PHYSICAL`.

## Protocolo de comparação (obrigatório)

- Mesma frase, mesmo build, mesmo estado (Supercérebro ON/OFF anotado).
- 3 medições antes, 3 depois. Reportar mediana **e** as 3 amostras, nunca só a melhor.
- Uma medição só não prova nada, e "parece mais rápido" nunca entra em relatório.
- Comando local determinístico (volume, brilho) e comando com LLM têm latências de
  ordens diferentes: **nunca comparar um com o outro**.

## Onde a latência costuma estar (hipóteses, não fatos)

Verificar antes de afirmar:
- caminho LLM sendo usado onde havia reflexo local determinístico (regressão de rota);
- espera de resposta completa antes de começar a falar, em vez de streaming;
- wake gate/Vosk carregando modelo no primeiro turno;
- fallback de TTS (`TTS_FALLBACK` no trace) porque a Kore falhou — isso é falha, não lentidão.

## Rótulo de saída

```
MEDIDO: <números, fonte, quantas amostras>
INFERIDO: <o que se deduziu dos números>
NÃO MEDIDO: <trechos sem instrumentação — normalmente T4>
```
