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
        ├── PRODUCT/UI LEAD
        │    ├── Pixel Perfect Lead
        │    ├── Motion Lead
        │    ├── Widget Lead
        │    └── Visual QA Lead
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

## QA — prova que funciona

Functional QA (comandos/IPC/PC), Regression QA (impacto/known failures),
Performance QA (latência), Release QA (build final/E2E/relatório).

## Workers

Executores especializados (React, CSS, Python, IPC, Voice, Browser, Windows,
Memory, Testing, Pixel Perfect, Motion, Widget). Workers não falam com o Alex:
`Worker → Lead → Chief of Staff → Alex`.

## Como isto se liga aos agentes que já existem no projeto

O projeto já tem uma hierarquia de agentes nomeados e configurados, definida em
`.claude/rules/time-zara.md` ("Time ZARA — 9 papéis"), com dono fechado por
arquivo. Essa estrutura **não é substituída** — os Leads deste modelo roteiam
trabalho para esses agentes já existentes em vez de inventar agente novo:

| Lead (este modelo)        | Agente real no projeto                                    |
|----------------------------|-------------------------------------------------------------|
| Backend Lead / Frontend Lead / Automation Lead | `zara-engenheiro-execucao` (`core/ipc_handlers.py`, `core/action_registry.py`, `core/actions/*`) |
| Voice Lead                 | `zara-engenheiro-voz` (`core/voice_stt.py`, `core/voice_tts.py`, `core/gemini_live_voice.py`) |
| Automation Lead (áudio/mic) | `zara-engenheiro-audio` (`aecAudio.ts`, `core/windows_audio.py`) |
| Memory/Intelligence Lead / performance | `zara-engenheiro-latencia` (`core/model_router.py`, `[VOICE_TRACE]`) |
| Product/UI (todos os sub-leads) | `zara-engenheiro-interface` (`frontend/src/**`) |
| Release QA / Build         | `zara-engenheiro-build` (`build_exe.py`, `dist-sidecar/`, `ZARA_ACTIVE_BUILD.*`) |
| Functional/Regression QA   | `zara-qa-evidencia` (roda suíte, número exato) |
| Release QA (auditoria final) | `zara-build-auditor`, `zara-evidence-reviewer` |
| Chief of Staff (revisão hostil final) | `zara-revisor-hostil` |
| Diagnóstico read-only (antes de escrever) | `zara-readonly-architect`, `zara-regression-investigator` |

Não existem hoje agentes dedicados a "Pixel Perfect", "Motion" e "Widget" como
papéis isolados — esse trabalho cai em `zara-engenheiro-interface`, dividido em
tarefas pequenas por região (ver `WORKING_MODEL.md`, regra de UI). Se o volume
de trabalho visual justificar, o Chief pode propor esses papéis como agentes
novos — mas isso é decisão de escopo separada, não automática.

`core/ipc_handlers.py` e `frontend/src/main.ts` continuam como arquivos
disputados: trava por tarefa, nunca duas travas simultâneas (regra já vigente
em `time-zara.md`).

## Regras de comunicação

- Worker não fala com o Alex.
- Chief só interrompe o Alex por `OWNER REQUIRED` real (ver `WORKING_MODEL.md`).
- Toda entrega vira algo testável — nunca só relatório.
