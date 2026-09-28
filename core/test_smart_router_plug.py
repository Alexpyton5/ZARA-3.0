# core/test_smart_router_plug.py — testes do plug do roteador inteligente.
#
# Roda no Python do Alex (a zoe nao executa o Python dele):
#     python -m core.test_smart_router_plug
# feito pela zoe; a logica foi validada fora do PC e o Codex roda na suite.
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.model_router import ModelRouter, TaskType
from core.smart_router import CHAT, LEVE, PESADO, classify
from core.smart_router_plug import smart_router_enabled, suggest_task_types

falhas = []


def check(nome, cond):
    print(("OK  " if cond else "FAIL"), nome)
    if not cond:
        falhas.append(nome)


# 1. classificador: 13 casos
_cases = [
    ("oi, tudo bem?", False, None, CHAT),
    ("me conta uma piada", False, None, CHAT),
    ("o que você acha de futevôlei?", False, None, CHAT),
    ("bom dia zara", False, None, CHAT),
    ("que horas são?", False, None, CHAT),
    ("liga o ar condicionado", False, None, LEVE),
    ("pesquisa na internet quanto custa um voo pra salvador", False, None, PESADO),
    ("analisa esse texto e resume pra mim: " + "x" * 400, False, None, PESADO),
    ("cria um script em python que renomeia arquivos", False, None, PESADO),
    ("faz isso e depois me mostra o resultado", False, None, PESADO),
    ("compara esses dois modelos pra mim", False, None, PESADO),
    ("qualquer coisa", True, None, CHAT),
    ("pesquisa isso", False, "leve", "leve"),
]
for pedido, modo_chat, manual, esperado in _cases:
    check("classify(%r) == %s" % (pedido[:40], esperado),
          classify(pedido, modo_chat=modo_chat, motor_manual=manual) == esperado)

# 2. tradução classify -> TaskType
check("chat -> GENERAL_CHAT",
      suggest_task_types("oi, tudo bem?") == [TaskType.GENERAL_CHAT])
check("leve -> GENERAL_CHAT",
      suggest_task_types("liga o ar condicionado") == [TaskType.GENERAL_CHAT])
check("pesado com código -> [CODING, REASONING]",
      suggest_task_types("cria um script em python que renomeia arquivos")
      == [TaskType.CODING, TaskType.REASONING])
check("pesado sem código -> [REASONING]",
      suggest_task_types("pesquisa na internet quanto custa um voo pra salvador")
      == [TaskType.REASONING])
check("manual desconhecido -> GENERAL_CHAT (seguro)",
      suggest_task_types("qualquer coisa", motor_manual="xyz") == [TaskType.GENERAL_CHAT])

# 3. flag
os.environ.pop("ZARA_SMART_ROUTER", None)
check("flag desligada por padrão", smart_router_enabled() is False)
os.environ["ZARA_SMART_ROUTER"] = "1"
check("flag liga com ZARA_SMART_ROUTER=1", smart_router_enabled() is True)
os.environ.pop("ZARA_SMART_ROUTER", None)

# 4. classify_intent honra o hint (mecanismo real do ModelRouter)
router = ModelRouter()
msg = "oi, como voce esta hoje?"
hint = suggest_task_types("analisa esse relatorio de 40 paginas e resume os pontos criticos")
sem_hint = router.classify_intent(msg, {})
com_hint = router.classify_intent(msg, {"smart_router_hint": hint})
check("sem hint: comportamento antigo preservado",
      sem_hint == router.classify_intent(msg, None))
check("com hint: sugestão vai pra frente",
      com_hint[0] == TaskType.REASONING and com_hint[0] != sem_hint[0])

# 5. exigências duras (voz/ferramentas/privado) continuam vencendo o hint
com_voz = router.classify_intent(msg, {"smart_router_hint": hint, "voice_mode": True})
check("voice_mode vence o hint", com_voz[0] == TaskType.VOICE)

print()
print("TUDO VERDE" if not falhas else "%d FALHAS" % len(falhas))
raise SystemExit(1 if falhas else 0)
