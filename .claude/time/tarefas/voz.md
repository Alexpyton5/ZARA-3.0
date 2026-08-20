# TAREFA ATUAL — agente VOZ

TASK_ID: TASK-V001
STATUS: ABERTA
MODO: READ-ONLY — nao edite nenhum arquivo
ROLLBACK: nao se aplica, nada e escrito

## Por que esta tarefa existe

O `git status` mostra muito trabalho nao commitado em `core/`. Nao vou mandar
ninguem escrever por cima de trabalho pela metade — foi assim que nasceu o loop
de regressao que custou semanas ao Alex.

Preciso saber a baseline antes de autorizar escrita.

## O que responder, nesta ordem

**1. A suite passa hoje?** (faca primeiro — e a resposta mais barata)

```
.venv\Scripts\python.exe -m pytest -q
```

Reporte o numero exato. Falha vai com nome e motivo. "A maioria passou" e
resposta rejeitada.

**2. `core/mcp/` e `core/telegram_grupo.py` estao ligados ou sao orfaos?**

Ambos sao novos e nao rastreados. Alguem importa? Ou existem so no disco?

**3. Voz e texto compartilham a cadeia?** (so se sobrar folego)

Pegue "que horas sao", "diminua o volume", "abra o YouTube" e prove, lendo o
source, que percorrem a mesma ordem em `_process_voice_message` e em
`handle_send_message`. Divergiu em alguma? Qual?

## Como reportar

Mande para o CEO:
`mcp__ccd_session_mgmt__send_message` com
session_id = `local_c4b07745-444f-448d-af42-4f997ccbe6b3`

Nao espere terminar os tres. Mande o numero do pytest assim que tiver.

Formato: o de `.claude/time/voz.md`, com KNOWN_BROKEN presente.
