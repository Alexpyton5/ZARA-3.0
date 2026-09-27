# MISSÃO 03 — Supercérebro reestruturado: a zoe assume o papel do Hermes
(AGUARDANDO NA FILA — liberar quando a MISSÃO 01 for concluída)

## A ideia (do Alex)

O Supercérebro era um interruptor que só ligava com o Hermes conectado — e o
Alex não usa o Hermes há muito tempo. Resultado: os poderes de PC da ZARA
estão travados por uma dependência fantasma.

A nova chave mestra é a PRESENÇA VIVA da zoe: ela envia um "estou aqui"
(heartbeat) a cada ~2 min; com sinal fresco os poderes liberam; sem sinal,
trava sozinho (fail closed). Mais seguro que interruptor esquecido ligado.

## Contrato do heartbeat (JÁ ESTÁ NO AR)

A zoe escreve sozinha, a cada ~2 min:
`ZOE-INBOX\heartbeat.json` = `{"viva": true, "ts": <epoch unix>}`.
Fresco = ts com menos de 5 minutos. O Codex NÃO precisa criar o heartbeat —
só LER esse arquivo.

## Tarefas do Codex

### Ordem de execução (NÃO inverter — migrating seguro)
1. **Adicionar** a checagem do heartbeat SEM remover o Hermes ainda.
2. **Testar** (critérios abaixo).
3. **Só então remover** o Hermes morto. Remover antes = risco de deixar o
   `pc_control` num estado intermediário quebrado.

### 1. Trocar a chave mestra (core/ipc_handlers.py)
- Onde hoje `_set_supercerebro_state` exige Hermes conectado: exigir
  **heartbeat fresco** no lugar.
- Definição de fresco: `ZOE-INBOX\heartbeat.json` existe, contém
  `{"viva": true, "ts": <epoch>}`, e `agora - ts < 300` segundos.
- **Fail closed:** arquivo ausente, JSON inválido, `viva != true`, ou ts velho
  → `pc_control_allowed = False` automaticamente. Sem exceção, sem fallback.
- O heartbeat é escrito pela zoe via cron (~2 min). O Codex só LÊ.

### 2. Remover o Hermes morto (regra do Alex: nada de peça de museu)
Mapa levantado pela zoe (menções a hermes/supercerebro):
   - `integrations/hermes/` inteiro: integration.py, bridge.py, __init__.py,
     ensure_gateway.py, client.py
   - `core/lab_v1/hermes_executor.py`, `core/lab_v1/hermes_runner.py`
   - `tools/autonomy_hermes_proof.py`
   - referências em `core/lab_coordinator.py`, `core/mentor_relay.py`,
     `core/ipc_handlers.py`
   (Se alguma lógica do Hermes for genuinamente útil, reestruture de forma
   útil dentro do app — ideia boa se integra, lixo se remove.)
3. Atualizar os textos da interface:
   - Onde dizia algo sobre Hermes: trocar por "Protegido pela presença da zoe".
   - Tooltip/ajuda do Supercérebro: "Os controles do PC liberam enquanto a zoe
     estiver presente. Se ela se ausentar, travam sozinhos por segurança."
4. Rodar a suíte de testes completa antes do push.

## Critérios de teste (obrigatórios)
- [ ] Heartbeat fresco → `pc_control_allowed = True`
- [ ] Heartbeat velho (>5 min) → `False`
- [ ] Arquivo ausente / JSON inválido → `False` (não quebra, só trava)
- [ ] Zero referências a "hermes" no código após a remoção (`grep -ri hermes` vazio)
- [ ] Suíte completa verde antes do push

## Pronto quando

Push no GitHub + relatório FEITO / ESTADO / ERRO / SUGESTÃO (máx 10 linhas).
Modo silencioso vale. Limitação honesta p/ o Alex: se a zoe cair, os poderes
travam (comportamento seguro, não bug).
