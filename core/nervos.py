# nervos.py — protocolo dos nervos Ranger<->Megazord
# Lógica pura, zero dependências. Codado e testado pela zoe.
# Spec: SPEC-NERVOS.md

from datetime import datetime, timezone, timedelta
import json
import re

TIPOS = ("ordem", "pergunta", "resposta", "status", "alerta")
PRIORIDADES = ("normal", "urgente")
_ID_RE = re.compile(r"^nervo-\d{8}-\d{3}$")

_BRT = timezone(timedelta(hours=-3))


def agora_iso():
    return datetime.now(_BRT).isoformat(timespec="seconds")


def criar_envelope(de, para, tipo, assunto, corpo,
                   prioridade="normal", precisa_resposta=False,
                   seq=1, criado_em=None):
    """Monta um envelope de nervo válido. Levanta ValueError se inválido."""
    if tipo not in TIPOS:
        raise ValueError(f"tipo inválido: {tipo}")
    if prioridade not in PRIORIDADES:
        raise ValueError(f"prioridade inválida: {prioridade}")
    if not assunto or not corpo:
        raise ValueError("assunto e corpo são obrigatórios")
    data = (criado_em or agora_iso())[:10].replace("-", "")
    env = {
        "id": f"nervo-{data}-{seq:03d}",
        "de": de,
        "para": para,
        "tipo": tipo,
        "prioridade": prioridade,
        "assunto": assunto,
        "corpo": corpo,
        "criado_em": criado_em or agora_iso(),
        "precisa_resposta": bool(precisa_resposta),
    }
    validar_envelope(env)
    return env


def validar_envelope(env):
    """Confere um envelope. Devolve (ok, [erros])."""
    erros = []
    if not isinstance(env, dict):
        return False, ["envelope não é um objeto"]
    for campo in ("id", "de", "para", "tipo", "prioridade",
                  "assunto", "corpo", "criado_em", "precisa_resposta"):
        if campo not in env:
            erros.append(f"falta o campo: {campo}")
    if env.get("tipo") not in TIPOS:
        erros.append(f"tipo inválido: {env.get('tipo')}")
    if env.get("prioridade") not in PRIORIDADES:
        erros.append(f"prioridade inválida: {env.get('prioridade')}")
    if not _ID_RE.match(str(env.get("id", ""))):
        erros.append(f"id fora do formato: {env.get('id')}")
    return (len(erros) == 0), erros


def para_json(env):
    return json.dumps(env, ensure_ascii=False, indent=2)


def de_json(texto):
    env = json.loads(texto)
    ok, erros = validar_envelope(env)
    if not ok:
        raise ValueError("envelope inválido: " + "; ".join(erros))
    return env


def eh_urgente(env):
    return env.get("prioridade") == "urgente"
