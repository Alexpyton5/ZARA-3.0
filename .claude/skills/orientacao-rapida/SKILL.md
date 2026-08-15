---
name: orientacao-rapida
description: Reconstrói o contexto da ZARA no MENOR número de tokens possível no início de qualquer sessão ou tarefa, usando uma sequência fixa de checagens baratas em vez de explorar o repositório. Use SEMPRE como primeiro passo de qualquer trabalho na ZARA, antes de ler qualquer código.
---

# Orientação rápida

## Quando usar

- Primeira ação de qualquer sessão nova na ZARA.
- Retomada depois de compactação de contexto ou troca de assunto.
- Antes de abrir qualquer arquivo de source. Sempre antes, nunca depois.

O repositório tem 28.084 arquivos. Explorar é caro e não responde nada. A sequência abaixo
responde quase tudo por menos que uma única leitura de `core/ipc_handlers.py`.

## Sequência fixa (rodar nesta ordem, parar quando estiver claro)

1. **`git log --oneline -3`** — barato. Responde: o que entrou por último, quem escreveu.
2. **`git status --porcelain | wc -l`** — barato. Responde: quanto trabalho sujo existe.
   Número alto significa que há delta não commitado e o rollback precisa ser planejado antes
   de escrever qualquer coisa.
3. **`git branch --show-current` + `git tag --list "zara-3.0-*"`** — barato. Responde: onde
   estou e qual é a baseline recuperável.
4. **Relatório mais recente em `.zara-dev/reports/`** — médio. Listar por data
   (`ls -t .zara-dev/reports/ | head -3`) e ler apenas o primeiro. Responde: o que a última
   tarefa provou, o que ficou `KNOWN_BROKEN`, qual era o próximo passo menor.
5. **Tarefa aberta em `.zara-dev/tasks/`** — médio. Mesmo padrão: listar por data, ler uma.
   Responde: existe tarefa delimitada em aberto com `FILES_ALLOWED` e `ROLLBACK` definidos.
6. **`.zara-dev/CURRENT_STATE.md`** — médio. Só se os passos 4 e 5 não fecharem o quadro.
7. **`ls -t frontend/release*/ -d`** — barato. Responde: quais linhagens de build existem e
   qual é a mais recente. Necessário antes de qualquer pedido de teste físico.
8. **Um `Grep` dirigido** — só depois de 1 a 7, e só com alvo nomeado.

Custo alvo da sequência inteira: alguns milhares de tokens. Se passar disso, algo saiu do
roteiro.

## Mapa técnico (não redescobrir, já está verificado em 2026-08-12)

- **Dispatcher central:** `core/ipc_handlers.py`, ~2.800 linhas, classe `IPCHandler`.
  - Entrada de **texto**: `handle_send_message`.
  - Entrada de **voz**: `_process_voice_message`, alimentada por `_on_speech_recognized`
    (STT local) e `_on_gemini_live_turn` (Gemini Live, com wake gate).
- **Intents determinísticos:** `core/pc_voice_intent.py` (`PcVoiceIntentDetector`,
  `_LOCAL_DETERMINISTIC_ACTIONS`).
- **Autorização e execução:** `core/action_registry.py` + `core/actions/*.py`.
- **Camada de voz:** `core/voice_stt.py`, `core/voice_tts.py`, `core/gemini_live_voice.py`.
- **Instrumentação:** 14 marcadores `[VOICE_TRACE] stage=... result=...` em
  `core/ipc_handlers.py` e `core/gemini_live_voice.py`. São a primeira fonte em qualquer
  investigação de voz.
- **Frontend:** Electron + React/Vite em `frontend/src/`. Renderer nunca fala com o sidecar
  direto.
- **Builds:** 9 linhagens em `frontend/release*`, ~7,7 GB, **nenhuma com manifesto de
  identidade**. Por isso todo pedido de teste físico precisa de caminho absoluto e hash.
- **Git:** HEAD em `codex/zara-voice-human-loop-001`, baseline
  `zara-3.0-principal-2026-08-08`, resíduo `.git/AUTO_MERGE` presente, 11 worktrees.
- **Governança:** `.zara-dev/` (protegido, gitignored). Nunca limpar, resetar ou apagar.

## Prioridade permanente

Fase 1, na ordem: (1) voz Kore real na saída; (2) latência mínima; (3) microfone que ouve
Alex e não entra em loop com a própria voz; (4) voz → compreensão → execução real, inclusive
comandos compostos. Qualquer trabalho que não sirva a esses quatro itens precisa de
justificativa explícita.

## Regra de encerramento

Se depois desta sequência ainda não estiver claro o que fazer, **PERGUNTAR ao Alex**.
Uma pergunta objetiva custa menos que exploração no escuro e vale mais, porque Alex é a
autoridade final sobre direção. Explorar o repositório para adivinhar a intenção dele é o
gasto mais caro e mais inútil que existe neste projeto.

## O que NUNCA fazer

- Abrir `core/ipc_handlers.py` inteiro "para entender o projeto".
- Rodar busca ampla (`Glob **/*.py`, grep sem alvo) antes dos passos 1 a 7.
- Reler relatório que já está no contexto desta sessão.
- Assumir estado de build por memória. Sempre conferir a linhagem antes de citar um EXE.
- Substituir a pergunta ao Alex por mais 20 leituras especulativas.
