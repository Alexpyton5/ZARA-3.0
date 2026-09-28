"""Portão de autoupdate seguro com rollback provado.

Peça da ZARA para o Lab Vivo (MISSÃO GIGANTE 2, Fase C): o Lab puxa uma
atualização, testa nos gates e publica sozinho — e se quebrar, VOLTA ATRÁS
com prova, em vez de deixar o app num estado quebrado.

Lógica pura: sem rede, sem chamar modelo nenhum, sem custo. Quem usa o portão
injeta como o mundo real funciona:

    read_fn(path) -> str | None      lê o conteúdo atual (None = não existe)
    apply_fn(path, content) -> None  escreve o conteúdo novo
    remove_fn(path) -> None          apaga o arquivo (desfaz uma criação)
    verify_fn() -> (bool, str)       os gates: (passou?, detalhe)

Fluxo: snapshot -> aplica -> verifica -> se falhou, rollback + prova -> veredito.

Regras que o portão garante:
  1. Nada é aplicado sem snapshot tirado ANTES.
  2. Rollback restaura na ordem reversa da aplicação.
  3. Arquivo que não existia volta a não existir (remove, não deixa lixo).
  4. O rollback é PROVADO: hash depois do restore == hash do snapshot.
  5. Plano vazio é recusado (nada a fazer não é update).
  6. Tudo fica no diário (journal): auditável do começo ao fim.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class GateVerdict:
    """Resultado de uma tentativa de update pelo portão."""

    approved: bool            # True = gates passaram, update ficou valendo
    rolled_back: bool         # True = deu ruim e o rollback restaurou tudo
    journal: List[dict] = field(default_factory=list)  # trilha auditável
    detail: str = ""          # resumo em linguagem simples


class AutoUpdateGate:
    """O portão. Criado uma vez, reutilizável para vários updates."""

    def __init__(
        self,
        read_fn: Callable[[str], Optional[str]],
        apply_fn: Callable[[str, str], None],
        remove_fn: Callable[[str], None],
    ) -> None:
        self._read = read_fn
        self._apply = apply_fn
        self._remove = remove_fn

    def _log(self, journal: List[dict], evento: str, **campos) -> None:
        entrada = {"ts": time.time(), "evento": evento}
        entrada.update(campos)
        journal.append(entrada)

    def propose(self, changes: Dict[str, str], journal: List[dict]) -> Dict[str, dict]:
        """Valida o plano e tira o snapshot de cada arquivo ANTES de aplicar.

        Devolve o plano: {path: {"novo": content, "novo_hash": ..., "antes": content|None,
        "antes_hash": ...|None}}. Plano vazio -> ValueError (regra 5).
        """
        if not changes:
            raise ValueError("plano vazio recusado: nada a fazer não é update")
        plano: Dict[str, dict] = {}
        for path, novo in changes.items():
            antes = self._read(path)
            plano[path] = {
                "novo": novo,
                "novo_hash": _sha256(novo),
                "antes": antes,
                "antes_hash": _sha256(antes) if antes is not None else None,
            }
            self._log(journal, "snapshot", arquivo=path,
                      hash_antes=plano[path]["antes_hash"],
                      existia=antes is not None)
        return plano

    def execute(
        self,
        changes: Dict[str, str],
        verify_fn: Callable[[], Tuple[bool, str]],
    ) -> GateVerdict:
        """Roda o ciclo completo: snapshot -> aplica -> verifica -> rollback se preciso."""
        journal: List[dict] = []
        try:
            plano = self.propose(changes, journal)
        except ValueError as e:
            return GateVerdict(approved=False, rolled_back=False,
                               journal=journal, detail=str(e))

        aplicados: List[str] = []
        try:
            for path, item in plano.items():
                self._apply(path, item["novo"])
                aplicados.append(path)
                self._log(journal, "aplicado", arquivo=path,
                          hash_depois=item["novo_hash"])
        except Exception as e:  # apply quebrou no meio: desfaz o que aplicou
            prova = self.rollback(plano, aplicados, journal)
            return GateVerdict(
                approved=False, rolled_back=True, journal=journal,
                detail=f"falha ao aplicar ({e}); rollback executado e provado: {prova['ok']}")

        try:
            ok, detalhe = verify_fn()
        except Exception as e:  # gate que explode conta como gate que falhou
            ok, detalhe = False, f"gate explodiu: {e}"
        self._log(journal, "verificacao", passou=ok, detalhe=detalhe)

        if ok:
            return GateVerdict(approved=True, rolled_back=False,
                               journal=journal,
                               detail=f"update aprovado: {detalhe}")

        prova = self.rollback(plano, aplicados, journal)
        return GateVerdict(
            approved=False, rolled_back=True, journal=journal,
            detail=f"gate reprovou ({detalhe}); rollback executado e provado: {prova['ok']}")

    def rollback(
        self,
        plano: Dict[str, dict],
        aplicados: List[str],
        journal: List[dict],
    ) -> dict:
        """Desfaz na ordem reversa e PROVA cada restore por hash (regra 4)."""
        prova = {"ok": True, "arquivos": {}}
        for path in reversed(aplicados):  # regra 2: ordem reversa
            item = plano[path]
            if item["antes"] is None:
                self._remove(path)  # regra 3: não existia -> volta a não existir
                depois = self._read(path)
                confere = depois is None
            else:
                self._apply(path, item["antes"])
                depois = self._read(path)
                confere = depois is not None and _sha256(depois) == item["antes_hash"]
            prova["arquivos"][path] = confere
            if not confere:
                prova["ok"] = False
            self._log(journal, "rollback", arquivo=path, prova_hash=confere)
        return prova
