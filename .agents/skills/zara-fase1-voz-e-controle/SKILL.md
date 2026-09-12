---
name: zara-fase1-voz-e-controle
description: Executa a Fase 1 da ZARA na ordem fixa — voz Kore na saída, latência mínima de resposta, microfone que ouve Alex sem entrar em loop com a própria voz da ZARA, e voz→execução real controlando o PC. Use para qualquer pedido de "consertar o que está quebrado", "fazer a ZARA funcionar", "melhorar a voz/latência/microfone" ou "ela não executa o que eu falo". Esta skill define O QUE arrumar e em QUE ORDEM; ela é o filtro que impede voltar ao loop de conserta-um-quebra-outro.
---

# ZARA Fase 1 — ouvir, raciocinar rápido, controlar o PC

## Objetivo declarado por Alex (2026-08-12)

> "Fazer ela ouvir, raciocinar rápido e controlar o PC por voz. Depois disso a gente cuida do resto."

Alex quer parar de depender do uso manual do computador **ainda nesta fase**.

## Ordem fixa. Não negociar, não paralelizar, não pular.

```
F1.1  VOZ KORE  →  F1.2  LATÊNCIA  →  F1.3  MICROFONE SEM LOOP  →  F1.4  VOZ → AÇÃO REAL
```

Um marco só abre quando o anterior tem `VOICE_PHYSICAL` confirmado por Alex.
Se um marco posterior parecer "fácil de já resolver junto", **não resolva**. Foi exatamente
isso que produziu o loop de brilho/volume/YouTube/night light por semanas.

## Filtro de escopo (rodar mentalmente antes de cada edição)

1. Este arquivo pertence ao marco atual? Se não → não toca.
2. Isto é a menor mudança que testa a hipótese? Se não → reduz.
3. Existe rollback nomeado? Se não → para.
4. Sei qual comando físico prova ou refuta isto? Se não → para e descobre primeiro.

Qualquer "já que estou aqui" é violação.

---

## F1.1 — Voz Kore de verdade

**Objetivo:** a saída falada da ZARA é a voz Kore, consistentemente, no candidato empacotado.

Investigar nesta ordem:

1. `core/gemini_live_voice.py` — qual voz é pedida, se é configurável, se há fallback silencioso
2. `core/voice_tts.py` — qual engine de TTS é realmente usada em runtime
3. `core/ipc_handlers.py::_speak_response` — qual caminho de fala é chamado por resposta
4. `_speak_windows_sapi` em `core/ipc_handlers.py` — fallback SAPI do Windows
5. `handle_engine_change` / `handle_engine_list` / `_persist_engine_preference` — seleção e persistência de engine
6. `frontend/src/renderer/components/zara/ZaraControlCenter.tsx` — o que a UI seleciona

**Modo de falha mais provável:** fallback silencioso. A ZARA pede Kore, falha (chave, rede,
sessão Live não abriu) e cai em SAPI sem avisar. Alex ouve outra voz e não sabe por quê.

**Correção mínima esperada:** o fallback tem de ser **audível e explícito** no log e no estado
de UI (`voz=kore` vs `voz=sapi_fallback motivo=<x>`). Nunca silencioso.

**Aceitação:** `VOICE_PHYSICAL` — Alex fala uma frase, ouve Kore, e o log mostra `voz=kore`.
Se cair em fallback, a ZARA diz por quê.

---

## F1.2 — Latência mínima

**Objetivo:** menor tempo possível entre Alex parar de falar e a ZARA começar a agir/responder.

**Antes de otimizar, medir.** Instrumentar timestamps por estágio usando o formato existente:

```
[VOICE_TRACE] stage=<X> result=<Y> ms=<delta_desde_estagio_anterior>
```

Estágios já presentes em `core/ipc_handlers.py`:
`WAKE_EVENT`, `WAKE_GATE`, `STT_RESULT`, `NORMALIZED_TEXT`, `INTENT_MATCH`,
`ACTION_DISPATCH`, `BARGE_IN`, `FINAL_RESPONSE`.

Faltam e devem ser acrescentados: fim da fala do usuário, primeiro byte de TTS, início do áudio.

**Ganho estrutural mais barato (fazer antes de qualquer micro-otimização):**
comando local determinístico **não deve tocar em LLM**. A cadeia já tenta intent antes do
modelo — confirmar que para os comandos do dia a dia o `INTENT_MATCH` casa e o LLM nunca é
chamado. Um comando local que cai no LLM custa segundos e é a maior fonte de lentidão.

Depois disso, atacar por ordem de custo medido, um estágio por vez.

**Aceitação:** tabela de ms por estágio antes/depois, no mesmo candidato, mais confirmação
física de Alex de que "ficou mais rápido".

---

## F1.3 — Microfone sem loop com a própria voz

**Objetivo:** a ZARA ouve Alex e **não** se escuta.

Modos de falha a distinguir (não confundir):

- **self-hearing:** o mic capta o alto-falante e a ZARA transcreve a própria fala
- **wake loop:** a própria fala da ZARA contém "Zara" e reativa o wake
- **barge-in quebrado:** Alex fala por cima e o TTS não para
- **mic mal calibrado:** corta a fala de Alex cedo demais ou tarde demais

Pontos de código:
- `core/voice_stt.py` — captura, VAD, limiares, janela de silêncio
- `core/gemini_live_voice.py` — `_on_gemini_live_interrupt`, `interrupt_speech`
- `core/ipc_handlers.py::_on_gemini_live_turn` — gate de wake (`_WAKE_PREFIX_RE`,
  `_gemini_wake_armed_until`, janela de 8s) e o atalho de parada
  (`pare|parar|interrompa|interromper|chega`)
- `_process_voice_message` bloco `finally` — `resume_listening(require_wake_word=True)`
- `handle_interrupt` / `tts_manager.interrupt()`

**Regra:** enquanto a ZARA fala, a ingestão de STT tem de estar suprimida ou o áudio de
saída tem de ser cancelado da entrada. Se a supressão for por tempo, ela é frágil — preferir
gate por estado real de reprodução.

**Aceitação:** `VOICE_PHYSICAL` — a ZARA fala uma resposta longa e (a) não se transcreve,
(b) não reativa o wake sozinha, (c) "Zara, pare" corta o áudio na hora.

---

## F1.4 — Voz → ação real no PC

**Objetivo:** o que Alex fala, a ZARA executa de verdade, incluindo comando composto.

Regras herdadas que valem aqui:

- voz e texto usam a **mesma** cadeia de intents (ver `.Codex/rules/path-rules/backend-core.md`)
- ação local determinística **não** depende do Supercérebro
- resposta de sucesso vem do executor, nunca de modelo

Método obrigatório por comando que falha:

1. rodar a **mesma frase** por texto e por voz no **mesmo** candidato
2. ler os `[VOICE_TRACE]` e achar o primeiro estágio que diverge
3. classificar: não ouviu / não transcreveu / não casou intent / casou mas bloqueou /
   executou mas falhou / executou mas mentiu na resposta
4. corrigir **um** comando por vez, com micro smoke, antes de ir para o próximo

Ordem de cobertura sugerida (do mais usado ao menos):
volume → brilho → night light → abrir app → YouTube abrir/buscar/tocar/pausar/próximo →
janelas (minimizar/maximizar/focar) → arquivos → lembretes → composto de 2–5 ações.

**Sobre "100% do PC":** capacidade nova entra **depois** que o núcleo acima estiver estável.
Ampliar cobertura antes de estabilizar é o loop de novo. Registrar as capacidades pedidas em
backlog, não implementar por impulso.

**Aceitação por comando:** `VOICE_PHYSICAL` no candidato nomeado, com a mudança observada no
Windows — não na frase que a ZARA falou.

---

## Loop de auto-correção (com portão físico)

1. rodar suíte/build primeiro e capturar o erro exato
2. ler o traceback, localizar arquivo/linha
3. menor alteração cirúrgica possível
4. rodar de novo para validar
5. se falhar 2 vezes na mesma hipótese → `BLOCKED`, reportar, mudar de abordagem
6. **verde não fecha a tarefa** — empacotar candidato com identidade e pedir 1–3 testes físicos

Gates:

```
python -m pytest -q
python -m ruff check main.py core memory integrations tests build_exe.py
python -m compileall -q main.py core memory integrations tests build_exe.py
```

```
npm ci && npm run typecheck && npm run lint && npm run build
```

Sempre com o toolchain do projeto, por caminho explícito. Nunca o Python do Hermes.

## O que NUNCA fazer nesta fase

- trabalhar em dois marcos ao mesmo tempo
- adicionar feature nova de roadmap (WOW) antes de F1.4 fechar
- mexer em roteamento de modelo/provider para "melhorar" um comando local
- mexer em ambiente/dependências dentro de uma tarefa de correção
- pedir mais de 3 testes físicos por delta
- entregar relatório sem `KNOWN_BROKEN`
- dizer "corrigido" com evidência abaixo de `PHYSICAL_BY_ALEX` para comportamento de UX
- gerar candidato novo sem `BUILD_INFO.json`
