# CONSELHEIRA — chat com a zoe dentro da ZARA

É a visão "Jarvis" do Alex: um painel de conversa contínua dentro do app ZARA
onde a **zoe** (assistente Muse) atua como **conselheira/CEO**. Cada mensagem
do Alex viaja por e-mail com um snapshot do estado da ZARA anexado; a zoe lê,
responde no formato da ponte, e a ZARA importa a resposta para o painel.

> Nada aqui usa API paga, Model API da Meta ou modelo local fingindo ser a
> zoe. O transporte é o Gmail, através de um adaptador injetável.

## Como funciona

1. O Alex escreve no painel **CONSELHEIRA** (navegação lateral do app).
2. O backend (`core/ipc_handlers.py`) enfileira a mensagem no `ChatRelay`
   com um contexto da ZARA anexado (data/hora, sistema, estado da ponte).
3. A cada sincronização, as mensagens pendentes são enviadas por e-mail para
   **zoeeproject@gmail.com** com o assunto `[ZARA-CHAT] <chat_id> <trecho>`.
4. A zoe verifica essa caixa, lê e responde ao e-mail incluindo o bloco
   `[ZARA-CHAT-REPLY]`.
5. A ZARA importa a resposta na próxima sincronização e exibe no painel.

Enquanto o painel está aberto, a sincronização é automática (ver padrão de
frequência abaixo); há também um botão de sincronizar manualmente.

## Protocolo da ponte

| Elemento | Valor |
|---|---|
| Assunto de saída | `[ZARA-CHAT] <chat_id> <trecho da mensagem>` |
| E-mail destino | `zoeeproject@gmail.com` |
| Bloco de resposta | `[ZARA-CHAT-REPLY]` … `[/ZARA-CHAT-REPLY]` |
| Campos da resposta | `chat_id:` + `reply:` |
| Idempotência | `seen.json` — cada e-mail é processado uma única vez |
| Fila local | `%LOCALAPPDATA%/ZARA3/data/ceo-relay/chat/` (`outbox/`, `sent/`, `archive/`, `thread.jsonl`) |

Corpo do e-mail enviado (resumo):

```
[ZARA-CHAT] Conversa com a Conselheira (zoe)

chat_id: CHAT-...

## Contexto da ZARA
<snapshot do estado>

## Mensagem do Alex
<texto>

---
Responda a este e-mail mantendo o assunto e incluindo o bloco:
[ZARA-CHAT-REPLY]
chat_id: <id>
reply: <sua resposta para o Alex>
[/ZARA-CHAT-REPLY]
```

## Padrões decididos com o Alex (2026-09-26)

1. **Frequência de checagem: a cada 5 minutos.** Está como padrão no código
   (`CHAT_CHECK_INTERVAL_SECONDS = 5 * 60` em
   `core/lab_ceo_gmail_bridge.py`); o painel usa esse valor no
   temporizador de auto-sincronização.
2. **E-mail da ponte: `zoeeproject@gmail.com`.** É o Gmail conectado — a
   caixa que a zoe verifica. Padrão em `CEO_MAILBOX_DEFAULT`, usado pelo
   `ChatRelay` e pelo `CeoRelay` como destinatário dos e-mails.
3. **Autonomia total da zoe.** Ela é a CEO e o cérebro: decide tudo, **sem
   gate de confirmação por padrão**. Pedidos e decisões continuam sendo
   registrados na fila local (`outbox/` → `sent/` → `archive/`) e no
   `thread.jsonl`, ou seja, tudo é auditável — mas nada fica travado
   esperando o Alex confirmar para valer.

## Como ligar o CeoMailAdapter ao Gmail real (tarefa do Alex/OpenCode)

Hoje o `ChatRelay` usa o `LoggingStubAdapter` (só registra localmente, sem
rede) — ideal para desenvolver e testar. Para produção:

1. No código do painel **Comunicações** da ZARA existe a conexão Gmail real.
   Crie uma classe que implemente o protocolo `CeoMailAdapter`
   (`core/lab_ceo_gmail_bridge.py`):
   - `send(to, subject, body) -> str` — envia o e-mail, retorna o id;
   - `search(query, max_results=20) -> list[dict]` — cada item com
     `message_id`, `subject`, `body`, `date`;
   - `mark_read(message_id) -> None` — marca como lida (best-effort).
2. Em `core/ipc_handlers.py`, na função `_get_chat_relay()`, instancie o
   `ChatRelay` passando `adapter=<sua implementação>`. O ponto está marcado
   com `TODO (Alex/OpenCode)` no código.
3. Pronto: o painel passa a enviar/receber de verdade, sem mudar mais nada.

## Arquivos

- `core/lab_ceo_gmail_bridge.py` — ponte (pedidos de decisão + chat da
  Conselheira); só stdlib.
- `core/ipc_handlers.py` — handlers `conselheira-send`, `conselheira-sync`,
  `conselheira-messages`, `conselheira-status`.
- `frontend/src/renderer/components/zara/ConselheiraPanel.tsx` — painel.
- `frontend/src/renderer/components/zara/ZoeAppPanel.tsx` — aba ZOE (app da
  zoe embutido via `<webview>`).
- `frontend/src/renderer/lib/zoeConfig.ts` — URL do app da zoe
  (`ZOE_APP_URL`) e partição persistente.
- `frontend/src/renderer/components/zara/ZaraControlCenter.tsx` — itens
  `CONSELHEIRA` e `ZOE` na navegação.
- `frontend/src/renderer/styles/globals.css` — estilos da aba ZOE.
- `frontend/src/preload.ts` — API `window.zaraIPC.conselheira`.
- `frontend/src/main.ts` — canais IPC `conselheira-*` + `webviewTag: true`
  (necessário para a aba ZOE).
- `tests/test_conselheira_chat.py` — testes do fluxo de chat.
- `tests/test_lab_ceo_bridge.py` — testes do fluxo de decisão (copiado do
  pacote entregue).

## Aba ZOE — o app da zoe embutido na ZARA

Além do painel CONSELHEIRA, a navegação lateral tem a aba **ZOE**: ao clicar,
o app web da zoe (`https://muse.ai`, configurável em `ZOE_APP_URL` no arquivo
`frontend/src/renderer/lib/zoeConfig.ts`) abre **embutido dentro da própria
janela da ZARA**, usando a tag `<webview>` do Electron com sessão persistente
(`partition="persist:zoe"` — o login é feito uma vez e mantido).

**Honestidade técnica — o que cada aba é de verdade:**

| | Aba ZOE | Painel CONSELHEIRA |
|---|---|---|
| Quem responde | A zoe de verdade: mesma conta, mesma memória, mesmos conectores (Gmail, agenda etc.) | A zoe de verdade, via ponte Gmail |
| A zoe enxerga o estado da ZARA? | **Não** — a visão embutida é visual, isolada do app | **Sim** — cada mensagem leva um snapshot da ZARA anexado |
| O Lab age sobre as respostas? | **Não** | **Sim** — decisões e respostas voltam para o painel/Lab |
| Latência | Tempo real (é o app web) | Minutos (sincronização a cada 5 min) |

**As duas abas juntas são a experiência Jarvis**: na aba ZOE você conversa
com a zoe com tudo o que ela já sabe sobre você; no painel CONSELHEIRA a
conversa acontece nos dois sentidos, com a ZARA enviando contexto e recebendo
orientações que o Lab pode executar. A interface não promete nada além disso.

## Testes

```bash
python -m pytest tests/test_conselheira_chat.py tests/test_lab_ceo_bridge.py -q
```
