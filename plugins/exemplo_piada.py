"""Plugin de exemplo — prova de que o sistema de plugins funciona de verdade."""
from core.action_registry import ActionResult, action

_PIADAS = [
    "Por que o programador foi ao médico? Porque tinha um bug.",
    "O que o SSD disse pro HD? Você é meio lento, né?",
]


@action(
    name="exemplo_piada",
    category="plugin",
    description="Conta uma piada curta (plugin de exemplo)",
    risk="LOW",
    capability="READ_ONLY",
)
def exemplo_piada_action() -> ActionResult:
    import random
    return ActionResult(success=True, output=random.choice(_PIADAS))
