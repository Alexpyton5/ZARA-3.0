# MISSÃO 03 — Supercérebro local: a chave é do Alex
(NA FILA — só abrir depois da MISSAO-REBUILD-A709B02-20260928)

## ATENÇÃO — esta versão SUBSTITUI a anterior
A versão anterior desta missão (heartbeat da zoe como chave mestra) foi
REJEITADA pelo Alex em 27/09 ~19:45 -03. NÃO implementar heartbeat como chave.
O que vale é só o que está escrito abaixo.

## A decisão do Alex (27/09 ~19:45 -03)
- O app NÃO depende de ninguém: sem Hermes, sem zoe, sem heartbeat como chave.
- Supercérebro = chave LOCAL do Alex: ele LIGA enquanto monitora o app,
  DESLIGA quando opera sozinho. Padrão: DESLIGADO.
- Ação perigosa SEMPRE pergunta pra ele na hora, mesmo com a chave ligada.
- Auto-desliga ao travar o PC ou após tempo sem ele usar (idle).
- O heartbeat da zoe continua existindo, mas SÓ como ronda dela — nada no app
  depende dele.

## Tarefas do Codex

### 1. Arrancar o Hermes morto (regra do Alex: nada de peça de museu)
Mapa levantado pela zoe (menções a hermes/supercerebro):
- `integrations/hermes/` inteiro
- `lab_v1/hermes_*`
- `tools/autonomy_hermes_proof.py`
- referências em `core/ipc_handlers.py`, `core/lab_coordinator.py`, `core/mentor_relay.py`

Remover tudo. Se algum import quebrar, o teste acusa — consertar pela causa raiz.

### 2. A chave local (o botão já existe — ligar de verdade)
- O botão supercérebro na sidebar + `core/supercerebro_grant.py` viram A chave
  mestra: `pc_control` e ações perigosas SÓ executam com a chave LIGADA.
- Padrão: DESLIGADO a cada início do app (fail closed — sem exceção, sem fallback).
- Ação perigosa (apagar arquivo, desligar o PC, alterar o sistema) SEMPRE pede
  confirmação pro Alex na hora, mesmo com a chave ligada.
- Auto-desliga: travou o PC (workstation lock) ou 15 min sem interação
  (ajustável) → a chave desliga sozinha.

### 3. PROIBIDO — quarentena (nunca reimplementar)
- Os símbolos `work_mode_active`, `work_mode_sentinel`,
  `_watch_supercerebro_work_mode` NÃO podem aparecer em nenhum arquivo.
  Se aparecerem, é contaminação: neutralizar na hora
  (`git checkout` da versão commitada) e avisar a zoe.
- NUNCA remover a trava fail-closed. Ela é a segurança; sem ela, nada liga.

## Critérios de aceite (teste de verdade, não promessa)
1. App abre com a chave DESLIGADA; `pc_control` bloqueado (o teste tenta e recebe
   bloqueio, não execução).
2. Alex liga a chave no botão → `pc_control` funciona.
3. Ação perigosa com a chave ligada → pede confirmação dele antes de executar.
4. Trava o PC (ou simula o idle) → a chave desliga sozinha; `pc_control` volta
   a bloquear.
5. Suíte focada verde + push do delta.

## Convergência
Relatório FEITO/ESTADO/ERRO/SUGESTÃO (máx 10 linhas) em
`ZOE-INBOX/concluidas/RELATORIO-MISSAO-03-*.md`.
