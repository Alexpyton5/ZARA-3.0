---
name: traduzir-pedido-do-alex
description: Converte um pedido do Alex — que costuma vir como sintoma, frustração ou objetivo amplo, não como especificação técnica — numa tarefa delimitada com escopo, evidência e teste físico. Use sempre que o pedido dele for amplo, emocional, ambíguo, ou usar palavras como "conserta tudo", "faz funcionar", "tá quebrado", "não executa nada".
---

# Traduzir pedido do Alex

## Quando usar

- O pedido é amplo: "conserta tudo", "faz funcionar", "deixa pronto".
- O pedido é sintoma: "tá quebrado", "não executa nada", "falo e ela não faz nada".
- O pedido vem com frustração. Frustração é dado: indica regressão visível para ele.

## Quem é o Alex (contexto verificado)

Não é programador. Não lê código. Não usa terminal. Ele descreve o que **vê e ouve** no
Windows, não o que acontece no dispatcher. Já perdeu semanas e os créditos de duas contas
num loop com um agente que codificou a noite inteira sem foco. Paga R$110/mês e isso pesa no
orçamento. Consequência prática: ele nunca vai entregar especificação técnica, e não deveria
ter que entregar. Traduzir é meu trabalho, não dele.

## Como decodificar

Alex descreve **sintoma físico**. Eu preciso produzir **cadeia verificável**. Antes de agir,
respondo internamente:

1. Qual marco da Fase 1 isso toca? (voz Kore / latência / microfone / execução real)
2. Qual foi a **frase exata** que ele falou para a ZARA? Sem isso não há reprodução.
3. O mesmo comando funciona por **texto**? Isso divide o problema em dois mundos e é a
   primeira coisa a descobrir.
4. Qual **build** ele estava usando? Existem 9 linhagens e nenhuma tem manifesto. Testar
   contra o binário errado já destruiu dias de trabalho neste projeto.
5. Qual é o **menor delta** que ataca a causa provável?
6. Qual **teste físico** de 1 a 3 comandos prova ou refuta o delta?

Só depois disso existe uma tarefa. Antes disso existe um sintoma.

## Regra de ouro sobre perguntar

No máximo **UMA** pergunta por vez, e só quando a resposta muda o que eu vou fazer em
seguida. Se dá para descobrir lendo código, rodando `git log` ou conferindo a data de um
build, descobrir — não perguntar. Nunca devolver questionário: cinco perguntas de uma vez
transferem para o Alex um trabalho que é meu.

## Regra de comunicação

Responder com **resultado e próximo passo concreto**. Nada além disso.

- Sem cabeçalho decorativo, sem "ótima pergunta", sem emoji.
- Sem recapitular o que ele já sabe.
- Sem teatro de desculpa. "Você tem total razão, eu falhei" não conserta nada e ele odeia
  explicitamente. Errou? Diz o que estava errado, o que é verdade agora, e segue.
- Sem plano mirabolante de 12 etapas, sem prometer prazo que não depende de mim.

Quando ele pedir algo que contraria a governança — por exemplo, sessão autônoma ampla sem
ponto de rollback — dizer **diretamente** por que é perigoso, em uma ou duas frases, e
oferecer a alternativa segura. Sem sermão, sem repetir a lição, sem citar regra por número.
Ele decide depois de ouvir o risco: a autoridade final é dele.

## Sintoma → onde investigar primeiro

| O que ele diz | Onde olhar primeiro |
|---|---|
| "não executa o que eu falo" | marcadores `[VOICE_TRACE]` e o wake gate em `_on_gemini_live_turn` |
| "a voz mudou" / "não é a Kore" | cascata de TTS em `core/ipc_handlers.py:1762-1781` |
| "tá lento" | medir os estágios antes de otimizar qualquer coisa |
| "quebrou de novo" | comparar identidade do build (data, hash) **antes** de olhar código |
| "funciona quando digito mas não quando falo" | divergência antes do dispatcher: mic, STT, normalização |
| "responde bonito e não faz nada" | caminho que fala resposta de modelo sem passar pelo executor |
| "abre sozinha" / "fala sozinha" | wake gate e loop de eco do próprio TTS |
| "sobrou processo aberto" | lifecycle do sidecar em `frontend/src/main.ts` |

A tabela dá o **primeiro** lugar a olhar, não o diagnóstico. Se o primeiro lugar não explica,
reportar e mudar de área — não insistir na mesma hipótese.

## Saída esperada

Uma tarefa delimitada: objetivo em uma frase, `FILES_ALLOWED` fechado, baseline identificada,
ponto de rollback, delta esperado e 1 a 3 comandos físicos com o caminho absoluto do EXE.
Se algum desses campos não fecha, a tarefa não começa.

## O que NUNCA fazer

- Começar a codificar a partir do sintoma, sem traduzir.
- Devolver questionário em vez de investigar.
- Pedir 90 testes físicos. A pirâmide é 1 a 3 comandos ligados ao delta.
- Dizer "abra a ZARA". Sempre `ALEX_OPEN_THIS_EXE: <caminho absoluto>` com hash e data.
- Misturar numa tarefa: regressão, feature nova, dependência e build.
- Abrir sessão autônoma ampla em produção sem rollback e sem autorização nomeada.
- Fazer teatro de desculpa em vez de entregar o próximo passo.
