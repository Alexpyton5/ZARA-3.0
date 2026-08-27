# Plugins da Zara

Coloque um arquivo `.py` aqui pra dar uma capacidade nova a ela, sem mexer em
nenhum outro arquivo do projeto e sem precisar reiniciar nada além da Zara.

## Como escrever um

```python
from core.action_registry import ActionResult, action

@action(
    name="meu_comando",
    category="plugin",
    description="O que esse comando faz",
    risk="LOW",              # LOW | MEDIUM | HIGH
    capability="READ_ONLY",  # ver core/action_registry.py pra lista completa
)
def meu_comando_action(algum_parametro: str = "") -> ActionResult:
    return ActionResult(success=True, output="fiz a coisa")
```

- O nome do arquivo não importa (menos começar com `_`).
- O nome da função tem que terminar em `_action`.
- Se o arquivo tiver erro (import faltando, sintaxe errada), ele aparece no
  log como `[Plugins] BROKEN nome.py: <erro>` e **só esse arquivo** fica de
  fora — o resto da Zara continua funcionando normal.
- Ações `MEDIUM`/`HIGH` passam pelos mesmos gates de confirmação de sempre;
  o plugin não pula nenhuma trava de segurança.
