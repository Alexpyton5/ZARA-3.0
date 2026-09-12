# OpenClaw abrindo página sozinho — investigação

STATUS: NÃO REPRODUZIDO DENTRO DO REPOSITÓRIO ZARA.

## O que foi verificado

1. **Busca textual completa** por `openclaw`, `webbrowser`, `startfile`,
   `shell.openExternal`, `BrowserWindow`, `Popen`/`subprocess` em `core/`,
   `frontend/src/`, `.zara-dev/`. O único código que menciona OpenClaw é o
   worker do LAB (`core/lab_worker_runtime.py`, `core/lab_coordinator.py`):
   ele invoca o CLI `openclaw` como **subprocesso headless**
   (`asyncio.create_subprocess_exec`, com `CREATE_NO_WINDOW` no Windows) para
   pedir uma "opinião de conselho" — não há chamada a `webbrowser.open`,
   `os.startfile` nem equivalente Electron em lugar nenhum do repo que
   mencione OpenClaw.
2. **Config gerada para OpenClaw** (`core/lab_worker_runtime.py:374-388`) já
   nega explicitamente a ferramenta `"browser"` ao agente
   (`tools.deny: [..., "browser", "canvas"]`) — o agente OpenClaw, quando
   chamado pela ZARA, não tem permissão de abrir navegador como ação.
3. **Nenhum processo `openclaw` rodando agora** (`wmic process where
   "commandline like '%openclaw%'"` — vazio) e **nenhuma porta de gateway
   OpenClaw ouvindo** (`netstat -ano` não mostra a porta padrão 19001 nem
   nenhuma porta associada).
4. **Nenhum atalho de inicialização do Windows** para OpenClaw — a pasta
   Startup do usuário só tem scripts `.vbs` do **Hermes** (projeto separado,
   não relacionado à ZARA), nada de OpenClaw.
5. **Nenhuma tarefa agendada** (`schtasks /query`) contendo "openclaw".
6. `openclaw agent --local` (o modo que a ZARA usa para o Conselho) não tem,
   pelo `--help` do CLI instalado (2026.7.1-2), nenhum comportamento
   documentado de abrir painel/gateway — isso é distinto de `openclaw
   dashboard` (que abre explicitamente uma "Control UI" no navegador) e de
   `openclaw daemon`/`openclaw gateway`, nenhum dos quais é chamado pelo
   código da ZARA.

## Conclusão honesta

Não encontrei, dentro do código da ZARA, nenhum caminho que abra uma aba/
janela de navegador para OpenClaw — nem automático, nem em loop. A ZARA só
chama o CLI OpenClaw como processo headless, uma vez por mensagem de
Conselho, sem flag de UI.

**NÃO PROVADO**: que o comportamento relatado por Alex vem deste repositório.
Hipóteses mais prováveis, fora do escopo do que dá para verificar por código:

- uma aba do Chrome/Edge fixada ou restaurada por sessão (reabre sozinha ao
  reiniciar o navegador, sem relação com a ZARA rodando);
- o próprio CLI `openclaw`, quando **instalado/configurado manualmente** por
  Alex fora do fluxo da ZARA (ex.: `openclaw configure`, `openclaw
  dashboard`), pode ter deixado um atalho, extensão de navegador, ou hábito
  de abrir `openclaw dashboard` que não está no histórico do Git;
- outra automação no Windows (Task Scheduler de outra ferramenta, extensão
  de navegador, atualização automática) sem relação com este repositório.

## O que ficou pronto por precaução, mesmo sem causa confirmada

Nenhuma mudança de código foi feita aqui porque não há o que corrigir sem
uma causa localizada — mudar algo "no escuro" arriscaria mascarar o
problema real. Recomendação para Alex, quando ele tiver 30 segundos:

1. Abrir o navegador, ver a URL exata da aba/página do OpenClaw que abre
   sozinha (endereço da barra, não só o título).
2. Rodar `openclaw daemon status` e `openclaw gateway status` (fora da
   ZARA, em um terminal comum) para confirmar se existe um gateway OpenClaw
   rodando em segundo plano por fora da ZARA.
3. Me dizer a URL exata — com isso dá pra saber se é o CLI, o navegador, ou
   outra coisa, sem mais suposição.

## Teste realizado

- Confirmar ausência de processo `openclaw` vivo: `wmic process where
  "commandline like '%openclaw%'"` → vazio.
- Confirmar ausência de porta de gateway ouvindo: `netstat -ano` → nenhuma
  porta OpenClaw.
- Confirmar ausência de atalho de startup: listagem da pasta Startup do
  usuário e da máquina → só Hermes.
- Confirmar ausência de tarefa agendada: `schtasks /query` → nenhuma linha
  com "openclaw".
