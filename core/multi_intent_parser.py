"""ZARA-MULTI-INTENT-PARSER-001 (Alex, 2026-08-28)

Peca ISOLADA e nao plugada. Faz parte do plano "Copiloto do Windows"
registrado em docs/audits/ e na memoria de backlog do projeto, mas Alex
decidiu adiar a integracao pra depois da Fase 1 (voz Kore, latencia,
microfone, voz->acao real). Nada aqui e chamado por core/ipc_handlers.py,
core/pc_voice_intent.py ou qualquer caminho de producao -- e so a peca em
si, testavel offline, sem tocar no que ja esta no ar.

Objetivo: receber uma frase composta em portugues e devolver uma LISTA de
acoes reconhecidas em ordem, no formato
[{"action": <nome>, "param": <str|None>}, ...], pronta pra virar JSON.

Design deliberado, mesma disciplina do resto do projeto:
- NAO chama modelo/rede. Reusa o mesmo PcVoiceIntentDetector 100%
  deterministico que ja decide comando de PC hoje (core/pc_voice_intent.py)
  -- nao inventa um classificador novo, nao duplica regex.
- NAO inventa acao. Uma clausula que o detector nao reconhece entra na
  lista com "action": None e "raw" com o texto original, nunca e descartada
  silenciosamente nem vira um chute.
- A separacao de clausulas reusa a MESMA logica de
  IPCHandler._try_compound_pc_intent (virgula/ponto-e-virgula/"e depois"/
  "depois", com o mesmo desdobramento por " e " solto quando cada pedaco
  sozinho ja e um comando reconhecido). Duas implementacoes divergentes da
  mesma regra de corte de frase seria o tipo exato de bug que as regras do
  projeto pedem pra evitar (voz e texto tem que compartilhar a mesma cadeia;
  aqui a mesma logica de corte tem que valer nos dois lugares que a usam).
"""
from __future__ import annotations

import json
import re

from core.pc_voice_intent import PcVoiceIntentDetector

_SPLIT_RE = re.compile(r"\s*(?:[,;]|\be\s+depois\b|\bdepois\b)\s*", re.IGNORECASE)
_SUB_SPLIT_RE = re.compile(r"\s+e\s+", re.IGNORECASE)
_LEADING_ZARA_RE = re.compile(r"^\s*zara\s*[,;:]?\s*", re.IGNORECASE)


def split_into_clauses(text: str) -> list[str]:
    """Corta uma frase composta em clausulas candidatas, sem decidir se cada
    uma e um comando valido -- so separa. Mesma regra de corte de
    IPCHandler._try_compound_pc_intent (core/ipc_handlers.py)."""
    raw = _LEADING_ZARA_RE.sub("", str(text or "").strip())
    parts = [p.strip(" .!?") for p in _SPLIT_RE.split(raw) if p.strip(" .!?")]
    return parts


def parse_multi_intent(text: str, *, pc_control_allowed: bool = True) -> list[dict]:
    """Converte uma frase composta numa lista ordenada de acoes reconhecidas.

    Cada item e {"action": str|None, "param": str|None, "raw": str}.
    "action" None significa que esta clausula nao bateu em nenhum comando
    conhecido -- quem consumir a lista decide se recusa o pedido inteiro
    (como o caminho de producao ja faz hoje) ou executa so o que reconheceu.
    Essa decisao NAO e tomada aqui de proposito: esta funcao so classifica.
    """
    detector = PcVoiceIntentDetector(pc_control_allowed=pc_control_allowed)
    parts = split_into_clauses(text)
    if len(parts) < 2:
        # Frase unica: ainda assim tenta reconhecer, pra funcao ser util
        # sozinha em vez de exigir sempre 2+ clausulas.
        parts = [p for p in [str(text or "").strip(" .!?")] if p]

    expanded: list[str] = []
    for part in parts:
        sub_parts = [s.strip(" .!?") for s in _SUB_SPLIT_RE.split(part) if s.strip(" .!?")]
        if len(sub_parts) >= 2 and all(detector.detect(s).is_pc_intent for s in sub_parts):
            expanded.extend(sub_parts)
        else:
            expanded.append(part)

    actions: list[dict] = []
    for clause in expanded:
        result = detector.detect(clause)
        if result.is_pc_intent and not result.blocked:
            actions.append({"action": result.action, "param": result.param, "raw": clause})
        else:
            actions.append({"action": None, "param": None, "raw": clause})
    return actions


def parse_multi_intent_json(text: str, *, pc_control_allowed: bool = True) -> str:
    """Mesma coisa que parse_multi_intent, mas ja serializada -- e o formato
    que Alex pediu explicitamente ("lista/array JSON")."""
    return json.dumps(
        parse_multi_intent(text, pc_control_allowed=pc_control_allowed),
        ensure_ascii=False,
    )
