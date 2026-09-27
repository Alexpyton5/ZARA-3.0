# ZARA — CEO Remoto via Relay (ponte Gmail) — 2026-09-26

A zoe (Muse) como CEO remota do Zara Lab, com o Gmail como transporte.
Suplemento do pacote `zara-living-team-20260926` — pode ser aplicado depois dele.

## Como funciona (o fluxo)

1. **ZARA precisa de uma decisão** (ex.: aprovar promoção de milestone,
   escolher entre opções de uma proposta, dúvida do modo autônomo).
2. A ZARA cria um **pedido de decisão** e envia por e-mail para o seu Gmail
   com assunto `[ZARA-CEO] CEO-... <título>`, num formato que a zoe entende.
3. **A zoe verifica essa caixa periodicamente**, lê o pedido com todo o
   contexto, decide e **responde o e-mail** com um bloco de decisão.
4. A ZARA lê a resposta, registra a decisão no Lab (feed da sala/missão) e
   segue — ex.: aprova o patch, escolhe a opção.
5. Tudo com marcador próprio no Gmail, fora da sua caixa de entrada.
   **Custo: R$ 0.** Latência: minutos (não é tempo real).

**Limites honestos:** a zoe não vê a tela da ZARA nem executa nada no seu PC —
ela é o cérebro remoto, não as mãos. Decisões irreversíveis continuam podendo
exigir sua confirmação (configure como quiser).

## Arquivos

- `core/lab_ceo_gmail_bridge.py` — a ponte (sem dependências, só stdlib).
  Segue o padrão do `mentor_relay.py` que já existe no projeto.
- `tests/test_lab_ceo_bridge.py` — 7 testes (rodam sem rede/credencial).

## Como instalar

1. Copie os 2 arquivos para os mesmos caminhos dentro da raiz canônica
   (`C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002`).
2. Valide: `python -m pytest tests/test_lab_ceo_bridge.py -q` → 7 passed.
3. **Ligar ao Gmail da ZARA** (tarefa para você/OpenCode — ver abaixo).
4. A zoe ativa a verificação periódica do lado dela (ela confirma a
   frequência com você antes de ligar).

## Ligando ao painel Comunicações (para o OpenCode)

O módulo define o contrato `CeoMailAdapter` com 3 métodos:

- `send(to, subject, body) -> str` — envia e retorna id da mensagem
- `search(query, max_results=20) -> list[{message_id, subject, body, date}]`
- `mark_read(message_id) -> None` — best-effort

Implemente um adaptador que use a **conexão Gmail já existente no painel
Comunicações** da ZARA e injete no `CeoRelay`:

```python
from core.lab_ceo_gmail_bridge import CeoRelay, CeoMailAdapter

class ZaraGmailAdapter:  # implementa CeoMailAdapter via painel Comunicações
    ...

relay = CeoRelay(adapter=ZaraGmailAdapter())
relay.request_decision(kind="milestone", title="Promover M010?",
                       context="...", question="Aprova a promoção?",
                       options=["Aprovar", "Rejeitar", "Adiar"])
relay.sync_outbox()   # envia pedidos pendentes
decisions = relay.sync_inbox()  # importa respostas da zoe (idempotente)
```

Sugestão: chamar `sync_outbox()` / `sync_inbox()` no loop do LabCoordinator
(hook de 3 linhas) ou num timer do backend a cada 5–10 min.

## Protocolo (para referência)

Pedido (ZARA → zoe): assunto `[ZARA-CEO] <request-id> <título>`; corpo com
Contexto, Pergunta, Opções e instrução de resposta.

Resposta (zoe → ZARA): reply mantendo o assunto, contendo o bloco:

```
[ZARA-CEO-DECISION]
request_id: CEO-<...>
decision: APPROVE | REJECT | DEFER | ANSWER
summary: <uma frase>
rationale: <motivo em 2-3 linhas>
[/ZARA-CEO-DECISION]
```

Respostas sem bloco válido são ignoradas; sem pedido correspondente, entram
como `matched=False` para revisão humana. Cada mensagem é processada uma única
vez (controle em `ceo-relay/seen.json`).

## Pendente (decisão do Alex)

1. **Frequência da verificação** da zoe (sugestão: a cada 15 min).
2. **O que o CEO pode decidir sozinho** vs. o que exige sua confirmação —
   hoje o módulo aceita qualquer decisão; o gate fica a seu critério.
