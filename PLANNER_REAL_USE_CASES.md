# Prova real do Planner ponta a ponta — ZARA 3.0

## O que foi provado de verdade (não mockado)

`Intent → Planner → PlanSteps → ToolRouter → Permission → ExecutionWrapper → Verifier → Result`

Rodado de verdade, sem mock nenhum, usando `list_folder_and_summarize_file`
(uma pasta temporária isolada criada só para o teste, nunca uma pasta real
do Alex):

```
accepted True None
PLAN_STATUS PlanStatus.COMPLETED
list      success=True  verificado=False
summarize success=True  verificado=False
```

`verificado=False` em ambos é o comportamento correto e esperado (não um
bug): nenhuma dessas duas tools tem um `verifier` configurado no
`ToolRouter` ainda, então ele honestamente reporta "não verificado" em vez
de fingir confirmação — exatamente o que `evidence.md` pede, e exatamente o
que a correção de hoje cedo (`ToolResult.verificado` default `False`) foi
feita para garantir.

Isso prova a cadeia completa pedida pela missão, com uma tool real, dado
real, resultado real.

## Achado durante a prova (bug real, corrigido)

`ToolRouter.route()` sempre falhava com `"No executor for '<nome>'"` para
qualquer uma das 142 tools adaptadas de `ActionRegistry` — o
`ToolDefinition.from_action_spec()` nunca ligava `.executor` a nada.
Corrigido em `core/tool_registry.py` (commit `601d36c`) delegando para
`ActionRegistry.execute()`, que já aplica os gates de
capability/risk/permission — nenhuma checagem foi pulada. Ver o commit para
detalhe completo. Isso não existia antes porque **nenhum código de produção
chamava `get_tool_router().route()` antes desta sessão** — o Planner foi o
primeiro consumidor real.

## Caso pedido pela missão — parcialmente bloqueado, causa raiz identificada

**"Abra o navegador, pesquise X e tire uma captura da página"**
(`browser_search_and_screenshot`) — o `Plan` é aceito e válido (testado com
router fake, `tests/test_planner_recipes.py`), mas a EXECUÇÃO REAL trava
indefinidamente.

### Diagnóstico (3 tentativas, depois `FAILED_AFTER_RETRIES` — sem mais loop)

1ª tentativa: pesquisa real no Google via o pipeline completo → travou (~4
min), matei o processo.
2ª tentativa: mesma coisa com `wait_until=domcontentloaded` e timeout menor
→ travou de novo.
3ª tentativa (diagnóstico isolado, não o pipeline completo): chamadas
`action_registry.execute()` sequenciais para `browser_navigate` +
`browser_screenshot`, fora do Planner → **trava igual, na segunda chamada**.

Isolado ainda mais:
- Um script Playwright cru (fora de `core/actions/browser.py`), navegando
  para `example.com` OU para uma busca real do Google → funciona rápido e
  correto nos dois casos.
- Uma ÚNICA chamada `action_registry.execute('browser_navigate', ...)` →
  completa rápido (retorna erro de validação de IP, mas não trava).
- DUAS chamadas sequenciais `action_registry.execute()` para ações
  `async_execution=True` (`browser_navigate` depois `browser_screenshot`)
  → a segunda trava sempre.

**Causa raiz, com confiança razoável**: `core/action_registry.py::execute()`
cria um eventloop asyncio NOVO a cada chamada
(`asyncio.new_event_loop()` + `run_until_complete`) e nunca fecha o
anterior. O browser/contexto Playwright de `core/actions/browser.py` é um
singleton de módulo (`_browser_instance`/`_browser_context`) criado dentro
do loop da PRIMEIRA chamada; uma segunda ação assíncrona, rodando num loop
novo e diferente, tentando reusar (ou recriar) esse estado, trava — um
problema clássico de objetos asyncio presos a um loop sendo usados a partir
de outro.

**Isso é pré-existente, não foi introduzido por esta sessão**, e não é bug
do Planner: o Planner só chama `ToolRouter.route()` uma vez por step, na
ordem certa — o travamento está uma camada abaixo, entre `ActionRegistry` e
o singleton de browser do Playwright.

**Por que não foi corrigido agora**: mexer no modelo de event loop de
`core/action_registry.py` (dispatcher central, ~2700 linhas, área do
ENGENHEIRO_EXECUCAO) ou no singleton de browser de `core/actions/browser.py`
é uma mudança de arquitetura compartilhada, não um ajuste pontual — errar
aqui pode quebrar QUALQUER ação assíncrona do sistema, não só browser. Por
regra do projeto (`.claude/rules/governance.md`), isso exige tarefa própria
e delimitada, não um patch de madrugada dentro de uma missão de Planner.

**Status**: `FAILED_AFTER_RETRIES` para execução real de 2 ações
assíncronas em sequência. `browser_search_and_extract` (a outra receita que
usa browser) tem o mesmo risco e não foi testada ao vivo por essa razão —
só validada com router fake.

## O que ficou provado vs o que ficou pendente

| Caso | Plano válido (mockado) | Execução real |
|---|---|---|
| `list_folder_and_summarize_file` | ✅ | ✅ **provado ao vivo** |
| `browser_search_and_screenshot` | ✅ | ❌ trava (bug pré-existente em ActionRegistry, não no Planner) |
| `browser_search_and_extract` | ✅ | não tentado (mesmo risco) |
| `screenshot_and_ocr` | ✅ | não tentado (captura de tela real do Alex sem necessidade) |

## Confirmações de segurança feitas durante a investigação

- O Chrome pessoal do Alex (`C:\Program Files\Google\Chrome\Application\chrome.exe`)
  nunca foi tocado — confirmado por `Get-CimInstance Win32_Process`, único
  processo, sem argumento de automação, intacto durante e depois de toda a
  investigação.
- A automação usa `chrome-headless-shell.exe` do Playwright (binário e
  perfil completamente separados, baixados pelo próprio Playwright), nunca
  o perfil real do Alex.
- Todo processo travado/órfão gerado durante o diagnóstico foi identificado
  e encerrado explicitamente (não deixado para trás).
