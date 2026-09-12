# Decisões puladas — Missão Noturna 04

## Decision 1

**Task**: Board 12 — criar adapter/facade real em torno de
`core/gemini_live_voice.py` para representá-lo como `AIProvider`.
**Reason decision is required**: esse arquivo é a voz ao vivo funcionando —
qualquer mudança nele, mesmo "só um wrapper", tem risco real de regressão
de voz, e a regra do projeto (`.claude/rules/path-rules/backend-core.md`,
`.claude/rules/time-zara.md`) é clara: nada de voz sem o
ENGENHEIRO_VOZ e sem teste físico depois.
**Options**: A) Alex autoriza uma sessão dedicada, com o
`zara-engenheiro-voz`, para extrair um adapter fino sem tocar a lógica
interna B) deixar como está até haver um consumidor real do `AIProvider`
(hoje não há nenhum)
**Recommended**: B — não vale o risco por um contrato que ninguém usa
ainda.
**Risk**: nenhum, por não ter sido feito — a voz continua exatamente como
estava.
**Work continued without decision**: sim — `MODEL_PROVIDER_CONTRACT.md`
documenta o contrato sem implementação, e `select_model()` funciona sem
precisar de nenhum `AIProvider` concreto.

## Decision 2

**Task**: Classificar retroativamente os testes existentes (~1600) como
`@pytest.mark.safe`/`@pytest.mark.sandbox` (pendência de missões
anteriores, não desta).
**Reason decision is required**: é trabalho de auditoria extenso, não uma
correção pontual — decidir a granularidade (por arquivo? por classe? por
teste?) é uma escolha de produto, não técnica.
**Options**: A) classificar por arquivo (rápido, impreciso) B) classificar
teste a teste (lento, preciso) C) não classificar, confiar só na trava de
`live` (o que já está em produção hoje)
**Recommended**: C por enquanto — a trava de hardware real já cobre o risco
que causou o incidente; classificação fina é polimento, não segurança.
**Risk**: nenhum novo — é o status quo.
**Work continued without decision**: sim — não foi tentado nesta sessão.

## Decision 3

**Task**: Implementar `LLMPlanner` (Planner que interpreta linguagem
natural e monta múltiplos passos sozinho).
**Reason decision is required**: exige decidir qual modelo usa
(`select_model` já permite pedir REASONING+TOOLS, mas escolher a política
de custo/latência para isso é uma decisão de produto), e exige um contrato
de "structured output" confiável — sem isso, é caminho aberto para o
Planner aceitar plano inventado por modelo sem validação real.
**Options**: A) autorizar uma sessão dedicada para `LLMPlanner`, com
`ModelPlanner -> parse -> validate_plan -> Plan`, nunca pulando validação
B) manter `RulePlanner` como único Planner até haver um caso de uso real
que precise de múltiplos passos vindos de linguagem natural
**Recommended**: B — não construir capacidade sem consumidor.
**Risk**: nenhum, por não ter sido feito.
**Work continued without decision**: sim — o resto da foundation
(`validate_plan`, `execute_plan`, `ToolRouter` boundary) funciona
igualmente bem para um `Plan` vindo de `RulePlanner` ou de um futuro
`LLMPlanner` — a interface não precisa mudar quando isso for decidido.
