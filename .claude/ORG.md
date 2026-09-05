# ZARA — Organização (Claude Operating Model)

Este arquivo é estável. Só muda por decisão explícita do Alex.

## Hierarquia

```
ALEX (Owner)
  └── CLAUDE CHIEF OF STAFF (sessão principal)
        ├── CTO
        │    ├── Backend Lead
        │    ├── Frontend Lead
        │    ├── Voice Lead
        │    ├── Automation Lead
        │    └── Memory/Intelligence Lead
        ├── PRODUCT/UI LEAD — "UI Director" (Opus 5)
        │    ├── Pixel-Perfect Analyst (Opus 5)
        │    ├── Frontend Executor (Sonnet)
        │    ├── Motion/Widget Executor (Sonnet)
        │    └── Visual QA / Final Judge (Opus 5)
        └── QA LEAD
             ├── Functional QA
             ├── Regression QA
             ├── Performance QA
             └── Release QA
```

## Owner — Alex

Define objetivo, prioridade de produto e resultado desejado. Não escolhe worker,
modelo, divisão de tarefa; não revisa diff a diff; não acompanha log.

## Chief of Staff — sessão principal do Claude

Interpreta o pedido do Alex, transforma em missão, quebra em briefs, escolhe
responsável, coordena execução, evita conflito de arquivo, exige evidência,
integra, decide a próxima tarefa, e só fala com o Alex quando necessário
(CHECKPOINT / BLOCKED / FINAL / OWNER SUMMARY — ver `WORKING_MODEL.md`).

Não delega por delegar: para tarefa pequena, o Chief pode executar direto.

## CTO — áreas técnicas

Backend, frontend técnico, Electron, Python, IPC, planner, model router, PC
control, browser control, arquivos, automação, memória, integrações,
performance, arquitetura.

## PRODUCT/UI — interface

Fidelidade ao MASTER, UX, animação, widgets, Core, Dock, tipografia,
materialidade, layout, microinteração.

MASTER (fonte visual absoluta, declarada pelo Alex):
`https://zara-titanium-emerald.p9jpk5w4m6.chatgpt.site/`
Fluxo: MASTER → Electron real → mesma viewport → screenshot → diferença →
correção → screenshot → validação. Não redesenhar, não "melhorar" — copiar.

**2026-09-04 (correção do Alex) — refinamento pixel-perfect usa cadeia
separada dentro do PRODUCT/UI LEAD**, papel batizado "UI Director": análise
visual, execução e julgamento nunca são o mesmo passo. Ver
`.claude/WORKING_MODEL.md` (seção "Refinamento visual pixel-perfect") para o
loop completo e `.claude/DECISIONS.md` para a decisão registrada.

- **UI Director** (Opus 5) — não escreve CSS; olha, mede, prioriza, escreve
  o brief e decide quando escalar/desescalar.
- **Pixel-Perfect Analyst** (Opus 5) — compara MASTER vs. Electron região por
  região, entrega brief objetivo, não edita arquivo.
- **Frontend Executor** (Sonnet) — executa o brief em React/CSS/Electron.
  Não reinterpreta o design.
- **Motion/Widget Executor** (Sonnet) — anima o que o Opus descreveu
  (Core, dock, hover, waveform, transições, microinterações).
- **Visual QA / Final Judge** (Opus 5) — compara MASTER vs. novo Electron e
  responde só `APPROVED` ou `REWORK` com as diferenças de maior impacto.
  Sonnet nunca aprova o próprio trabalho.

## QA — prova que funciona

Functional QA (comandos/IPC/PC), Regression QA (impacto/known failures),
Performance QA (latência), Release QA (build final/E2E/relatório).

## Workers

Executores especializados (React, CSS, Python, IPC, Voice, Browser, Windows,
Memory, Testing, Pixel Perfect, Motion, Widget). Workers não falam com o Alex:
`Worker → Lead → Chief of Staff → Alex`.

## Time novo — não é o time antigo com etiqueta trocada

**Correção do Alex (2026-09-04):** este é um time novo. Os Leads deste modelo
**não** são um apelido para os agentes antigos de `.claude/rules/time-zara.md`
("Time ZARA — 9 papéis"). Esses 9 agentes ficam **retirados** para trabalho
novo (motivo e detalhe em `.claude/DECISIONS.md`) — continuam existindo em
disco como histórico/leitura, mas o Chief of Staff não despacha mais tarefa
para eles.

Os limites de área do time novo também não são os mesmos do time antigo — por
exemplo o **Voice Lead** junta o que antes eram dois donos separados
(voz de saída/wake + microfone/eco), porque é assim que o Alex descreveu o
papel. Ver arquivo do agente para a área exata de cada Lead.

Agentes do time novo são criados **sob demanda**, um por vez, conforme o
trabalho chega naquela área — não os 13 de uma vez (regra 16 do modelo:
não sobre-delegar). Criados até agora:

| Lead (este modelo) | Agente novo                | Área de escrita                                                    |
|---------------------|------------------------------|---------------------------------------------------------------------|
| Voice Lead          | `voice-lead` (`.claude/agents/voice-lead.md`) | `core/voice_stt.py`, `core/voice_tts.py`, `core/gemini_live_voice.py`, `frontend/src/renderer/lib/aecAudio.ts`, `core/windows_audio.py` |

Os demais (Backend, Frontend, Automation, Memory/Intelligence Leads; UI
Director, Pixel-Perfect Analyst, Frontend Executor, Motion/Widget Executor,
Visual QA; Functional/Regression/Performance/Release QA) ainda não têm
agente próprio — são criados no momento em que uma tarefa real cair naquela
área, seguindo o mesmo padrão do `voice-lead.md`. Para a cadeia pixel-perfect
isso é a task UI-001 (ver `.claude/TASK_BOARD.md`), não a instalação da
política em si.

`core/ipc_handlers.py` e `frontend/src/main.ts` continuam como arquivos
disputados: trava por tarefa do Chief of Staff, nunca duas travas
simultâneas — regra que vale para o time novo inteiro, não só para o antigo.

## Regras de comunicação

- Worker não fala com o Alex.
- Chief só interrompe o Alex por `OWNER REQUIRED` real (ver `WORKING_MODEL.md`).
- Toda entrega vira algo testável — nunca só relatório.
