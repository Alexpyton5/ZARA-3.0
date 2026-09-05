"""ZARA-MEMORIA-AUTOMATICA-001 — ela guarda sozinha o que Alex diz sobre si.

Inspirado no Vellum, que extrai identidade, preferências e projetos da conversa
com origem e sem duplicar. A ZARA já tinha a gaveta certa
(`memory/user_memory.py`: fato, categoria, confiança, origem, confirmar,
corrigir, esquecer) — o que faltava era alguém **colocar coisa dentro**.

Hoje `user_memory.add()` só é chamado quando Alex pede explicitamente para
lembrar. Memória que só enche sob comando fica vazia: em meses de uso ele nunca
mandou guardar "prefiro respostas curtas", e mesmo assim isso é a coisa mais
importante que ele já disse.

**Por que por regra e não por modelo.** Vellum usa o modelo para extrair. Aqui
isso custaria uma chamada extra a cada frase, e Alex definiu velocidade como
objetivo permanente. Frase de preferência em português tem marcador explícito
("eu prefiro", "sempre que", "não quero", "de agora em diante"). Reconhecer o
marcador custa microssegundos e erra pouco. Preferimos guardar de menos com
precisão alta a guardar de mais e poluir.

Nada aqui fala com o Alex nem executa ação: só observa e anota.
"""
from __future__ import annotations

import re
import unicodedata

# Marcadores de PREFERÊNCIA — como ele quer as coisas.
_PREFERENCIA = (
    r"eu\s+(?:prefiro|gosto\s+de|n[ãa]o\s+gosto\s+de|odeio|detesto|adoro|quero|n[ãa]o\s+quero)",
    r"(?:de\s+agora\s+em\s+diante|a\s+partir\s+de\s+agora|daqui\s+(?:pra|para)\s+frente)",
    r"(?:sempre|nunca)\s+(?:que\s+)?(?:me|voc[êe]|fa[çc]a|fale|use|deixe|mande)",
    r"(?:me\s+poupe|me\s+avise|me\s+chame|me\s+mostre|me\s+diga)\s+\w+",
    r"n[ãa]o\s+(?:precisa|quero)\s+(?:ficar\s+)?\w+",
)

# Marcadores de FATO sobre ele — quem é, o que tem, o que faz.
_FATO = (
    r"eu\s+(?:sou|tenho|moro|trabalho|uso|fa[çc]o|estudo|nasci)\b",
    r"meu?\s+\w+\s+(?:é|e|se\s+chama)\b",
    r"minha\s+\w+\s+(?:é|e|se\s+chama)\b",
    r"eu\s+n[ãa]o\s+(?:sou|tenho|entendo|sei)\b",
)

# Marcadores de PROJETO/OBJETIVO — no que ele está metido.
_PROJETO = (
    r"(?:estou|to|tô)\s+(?:tentando|fazendo|construindo|criando|trabalhando)\b",
    r"(?:meu|nosso)\s+(?:objetivo|plano|projeto|foco)\b",
    r"(?:a\s+ideia|o\s+plano)\s+(?:é|e)\b",
)

# Coisas que NUNCA viram memória, mesmo casando com marcador acima.
_NAO_GUARDAR = (
    # segredo
    r"\b(?:senha|password|token|api[\s_-]?key|chave\s+api|cart[ãa]o|cpf|cvv)\b",
    # comando do momento, não fato duradouro
    r"^(?:zara[,\s]+)?(?:abre|abra|fecha|feche|toca|pausa|aumenta|diminui|liga|desliga|"
    r"minimiza|maximiza|coloca|p[õo]e|manda|responde|l[êe]|leia)\b",
    # pergunta não é afirmação
    r"\?\s*$",
)

_MIN_CARACTERES = 12
_MAX_CARACTERES = 240


def _sem_acento(texto: str) -> str:
    base = unicodedata.normalize("NFKD", str(texto or "").casefold())
    return "".join(c for c in base if not unicodedata.combining(c))


def _bate(padroes: tuple[str, ...], texto: str) -> bool:
    return any(re.search(p, texto, re.I) for p in padroes)


def classificar(frase: str) -> tuple[str, float] | None:
    """Devolve (categoria, confiança) se a frase merece virar memória.

    None significa "não guardar" — que é o resultado esperado na maioria das
    frases. Uma memória que guarda tudo não é memória, é transcrição.
    """
    texto = " ".join(str(frase or "").split())
    if not (_MIN_CARACTERES <= len(texto) <= _MAX_CARACTERES):
        return None

    if _bate(_NAO_GUARDAR, texto) or _bate(_NAO_GUARDAR, _sem_acento(texto)):
        return None

    # Ordem importa: preferência é o que mais muda o comportamento dela.
    if _bate(_PREFERENCIA, texto):
        return ("preference", 0.75)
    if _bate(_PROJETO, texto):
        return ("semantic_fact", 0.6)
    if _bate(_FATO, texto):
        return ("semantic_fact", 0.7)
    return None


def _raizes(frase: str) -> set[str]:
    """Palavras reduzidas ao começo, para "curtas" e "curtinhas" contarem igual.

    Sem isso a comparação falha justamente onde mais dói: Alex repete a mesma
    preferência com outras palavras ("respostas curtas", "respostas bem
    curtinhas") e a memória guarda as duas.
    """
    return {p[:4] for p in re.findall(r"[a-z0-9]{4,}", _sem_acento(frase))}


def _parecidas(a: str, b: str) -> bool:
    """Duas frases dizem a mesma coisa? Evita a memória encher de repetição."""
    ta, tb = _raizes(a), _raizes(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / min(len(ta), len(tb)) >= 0.7


def guardar_se_valer(user_memory, frase: str, origem: str = "conversa") -> dict | None:
    """Observa uma fala do Alex e guarda se for fato ou preferência.

    Silencioso de propósito: ela não anuncia que anotou. Anunciar a cada frase
    seria pior que não anotar.
    """
    if user_memory is None:
        return None

    classificacao = classificar(frase)
    if classificacao is None:
        return None
    categoria, confianca = classificacao

    texto = " ".join(str(frase).split())

    # Dedup contra o que já está guardado. Sem isto, "eu prefiro respostas
    # curtas" vira dez registros iguais em uma semana.
    try:
        existentes = user_memory.search(texto, category=categoria, limit=8) or []
    except Exception:
        existentes = []
    for item in existentes:
        anterior = str(item.get("fact") or item.get("texto") or "")
        if _parecidas(anterior, texto):
            return None

    try:
        return user_memory.add(
            texto, category=categoria, confidence=confianca, source=origem
        )
    except Exception:
        # Memória nunca pode derrubar uma conversa.
        return None
