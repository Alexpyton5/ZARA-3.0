# core/smart_router.py — Classificador do Roteador Inteligente da ZARA
# Lógica pura, zero dependências. Codado e testado pela zoe.
# Plugado no app via core/smart_router_plug.py (atrás da flag ZARA_SMART_ROUTER).
# Spec: SPEC-roteador-inteligente.md (ZOE-INBOX)

CHAT = "chat"      # bate-papo: motor mais RÁPIDO
LEVE = "leve"      # pedido fácil: motor leve
PESADO = "pesado"  # pedido difícil: motor pesado

# Pedido DIFÍCIL se contém qualquer um destes sinais (PT-BR)
_HARD_KEYWORDS = (
    "pesquis", "busc", "procur",           # pesquisa na internet
    "analis", "compar", "avali",            # análise
    "código", "codigo", "program", "script", "função", "funcao", "bug", "erro no",
    "resum", "sintetiz",                    # resumo de texto longo
    "planej", "roteiro", "cronograma",
    "traduz", "gerar", "crie um", "cria um",
    "internet", "google",
)

# Bate-papo: cumprimentos e conversa fiada (frases; "oi"/"olá" tratados à parte
# porque aparecem dentro de outras palavras: "depois", "dois")
_CHAT_KEYWORDS = (
    "bom dia", "boa tarde", "boa noite",
    "piada", "tudo bem", "como vai", "que você acha", "que voce acha",
    "conversa", "bate-papo", "bate papo",
)


def _is_greeting(t):
    padded = " " + t + " "
    return (" oi " in padded or " olá " in padded or " ola " in padded
            or t in ("oi", "olá", "ola"))


_TASK_VERBS = (
    "faça", "faca", "faz", "crie", "cria", "gere", "gera",
    "me mostra", "me mostre", "abre", "abra", "liga", "desliga",
)


def _contains_any(texto, palavras):
    return any(p in texto for p in palavras)


def _count_tasks(texto):
    # Conta tarefas: verbos de ação + conectores de múltiplas tarefas
    n = sum(1 for v in _TASK_VERBS if v in texto)
    n += texto.count(" e depois ") + texto.count(", depois ")
    n += texto.count(" e também ") + texto.count(" e tambem ")
    return n


def classify(pedido, modo_chat=False, motor_manual=None):
    """Devolve CHAT, LEVE ou PESADO. Se motor_manual vier preenchido, respeita ele."""
    if motor_manual:
        return motor_manual

    t = (pedido or "").strip().lower()
    if not t:
        return CHAT

    # 1. Bate-papo explícito
    if modo_chat or _is_greeting(t) or _contains_any(t, _CHAT_KEYWORDS):
        return CHAT

    # 2. Difícil: sinais fortes, texto longo ou 2+ tarefas
    if _contains_any(t, _HARD_KEYWORDS):
        return PESADO
    if len(t) > 300:
        return PESADO
    if _count_tasks(t) >= 2:
        return PESADO

    # 3. Pedido curto sem verbo de tarefa = conversa
    if len(t) < 60 and not _contains_any(t, _TASK_VERBS):
        return CHAT

    # 4. Resto = fácil
    return LEVE
