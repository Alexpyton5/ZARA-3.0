# O time de abas da ZARA

Cada aba do Claude Code é um membro do time, com **uma** função e **uma** área do código.
Ninguém escreve na área do outro. Isso existe para acabar com o loop de regressão:
conserta voz → quebra frontend → rebuild → volta tudo.

## Quem é quem

| Aba | Função | Mexe em |
|---|---|---|
| **CEO Mentor** | recebe o Alex, decide, distribui, cobra prova | nada de source |
| **Voz** | voz, intents, actions, dispatcher | `core/`, `tests/` |
| **Frontend** | tela, Electron, React | `frontend/src/` |
| **Build** | empacotar, validar, hash, candidato | `build_exe.py`, `tools/`, gates |

## Como abrir o time (Alex faz isto uma vez)

Abra uma aba nova do Claude Code **nesta mesma pasta** e cole a linha correspondente:

```
Você é o agente VOZ do time ZARA. Leia .claude/time/voz.md e assuma o papel.
```

```
Você é o agente FRONTEND do time ZARA. Leia .claude/time/frontend.md e assuma o papel.
```

```
Você é o agente BUILD do time ZARA. Leia .claude/time/build.md e assuma o papel.
```

Depois volte na aba do CEO e diga **"abas abertas"**. O CEO registra todo mundo e o time começa.

## Onde fica o QA e o Revisor

Não têm aba. São subagentes read-only que rodam **dentro** da aba do CEO, e já existem
em `.claude/agents/`:

- `zara-evidence-reviewer` — portão final, rejeita promoção de evidência e falso sucesso
- `zara-build-auditor` — confere identidade de artefato antes de teste físico
- `zara-regression-investigator` — rastreia uma falha física concreta
- `zara-readonly-architect` — mapeia a cadeia voz → dispatcher → executor

Quem não escreve source não precisa de aba. Aba é para quem edita arquivo, e só existe
para garantir **um escritor por área**.

## Onde fica a lista de tarefas

`.agent_context/BACKLOG.json` — já existe no projeto, criado pelo time do Hermes.
É o único estado que sobrevive quando o Claude Code fecha. O CEO lê de lá no começo e
grava de volta no fim.

Regra do backlog: **toda tarefa entregue tem que virar algo que o Alex consiga testar.**
Tarefa cujo entregável é um relatório não é tarefa, é preparação.

## Como o time conversa

Não é `@` de chat — é mensagem direta entre abas. O CEO manda a tarefa para a aba certa,
a aba trabalha e responde para o CEO. A resposta chega com link de volta, então dá para
seguir a conversa clicando.

O Alex fala **só com o CEO**. Não precisa vigiar as outras abas.

## Limites honestos

- Uma aba só trabalha quando **recebe** uma mensagem. Ninguém fica acordado esperando.
- Fechou o Claude Code, o time para. Não é serviço 24/7.
- Do trabalho, pelo claude.ai, **não** dá para ver estas abas. Elas rodam no PC de casa.
  Para acompanhar de fora, a ponte é o Telegram (`core/telegram_ponte.py`).
