"""SugestoesMomento — sugestões contextuais faladas/mostradas no momento certo.

Contrato:
  - recebe sugestões pendentes de um `diario` (qualquer objeto com
    `sugestoes_pendentes() -> list[dict]`);
  - só libera sugestão fora do silêncio noturno e com Alex ocioso o
    suficiente (`ler_ambiente()`);
  - agrupa por `chave_agregacao`, no máximo uma sugestão por chave e por
    chamada;
  - respeita limite diário (`limite_diario`) e nunca repete a mesma
    sugestão no mesmo dia (por `id`, ou hash do conteúdo quando não há
    `id`);
  - persiste o estado do dia (`shown_count`, `shown_ids`) em disco e reseta
    sozinho quando o dia vira.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from core.paths import data_dir
from core.perception.ambiente import ler_ambiente

# "noite" e "madrugada" == silêncio noturno (docs/proatividade_pesquisa.md, guard §4).
_PERIODOS_SILENCIOSOS = {"noite", "madrugada"}

DEFAULT_LIMITE_DIARIO = 5
DEFAULT_LIMITE_OCIOSIDADE = 30.0

ESTADO_ARQUIVO = "sugestoes_momento_state.json"


class SugestoesMomento:
    """Decide quais sugestões pendentes podem ser mostradas agora."""

    def __init__(
        self,
        diario: Any | None = None,
        estado_path: Path | None = None,
        limite_diario: int = DEFAULT_LIMITE_DIARIO,
        limite_ociosidade: float = DEFAULT_LIMITE_OCIOSIDADE,
    ) -> None:
        self.diario = diario
        self.limite_diario = limite_diario
        self.limite_ociosidade = limite_ociosidade
        self.estado_path = Path(estado_path) if estado_path is not None else (data_dir() / ESTADO_ARQUIVO)
        self._estado: dict[str, Any] = self._carregar_estado()

    # ------------------------------------------------------------------
    # Persistência de estado (por dia)
    # ------------------------------------------------------------------

    @staticmethod
    def _estado_inicial() -> dict[str, Any]:
        return {
            "date": time.strftime("%Y-%m-%d", time.localtime()),
            "shown_count": 0,
            "shown_ids": [],
        }

    def _carregar_estado(self) -> dict[str, Any]:
        if not self.estado_path.exists():
            return self._estado_inicial()
        try:
            with self.estado_path.open("r", encoding="utf-8") as f:
                estado = json.load(f)
        except (OSError, ValueError):
            return self._estado_inicial()
        if not isinstance(estado, dict) or "date" not in estado:
            return self._estado_inicial()
        estado.setdefault("shown_count", 0)
        estado.setdefault("shown_ids", [])
        return estado

    def _salvar_estado(self) -> None:
        try:
            self.estado_path.parent.mkdir(parents=True, exist_ok=True)
            with self.estado_path.open("w", encoding="utf-8") as f:
                json.dump(self._estado, f)
        except OSError:
            pass

    def _resetar_estado_se_novo_dia(self) -> None:
        hoje = time.strftime("%Y-%m-%d", time.localtime())
        if self._estado.get("date") != hoje:
            self._estado = self._estado_inicial()
            self._estado["date"] = hoje
            self._salvar_estado()

    # ------------------------------------------------------------------
    # Identidade de sugestão (id explícito, senão hash do conteúdo)
    # ------------------------------------------------------------------

    @staticmethod
    def _id_sugestao(sugestao: dict[str, Any]) -> Any:
        sugestao_id = sugestao.get("id")
        if sugestao_id is not None:
            return sugestao_id
        bruto = json.dumps(sugestao, sort_keys=True, default=str, ensure_ascii=False)
        return hashlib.sha256(bruto.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # API principal
    # ------------------------------------------------------------------

    def obter_sugestoes(self) -> list[dict[str, Any]]:
        """Retorna as sugestões liberadas para mostrar/falar agora (pode ser vazio)."""
        self._resetar_estado_se_novo_dia()

        if self.diario is None:
            return []

        pendentes = self.diario.sugestoes_pendentes()
        if not pendentes:
            return []

        ambiente = ler_ambiente()

        # Guard: silêncio noturno — nada é mostrado, nem contabilizado.
        if ambiente.periodo in _PERIODOS_SILENCIOSOS:
            return []

        # Guard: Alex ocupado (ociosidade insuficiente).
        ocioso = ambiente.ocioso_segundos if ambiente.ocioso_segundos is not None else 0.0
        if ocioso < self.limite_ociosidade:
            return []

        # Guard: limite diário já atingido.
        vagas = self.limite_diario - int(self._estado.get("shown_count", 0))
        if vagas <= 0:
            return []

        shown_ids: list[Any] = self._estado.setdefault("shown_ids", [])

        # Agrupamento por chave_agregacao: no máximo uma sugestão por chave,
        # e nunca repetir uma sugestão já mostrada hoje.
        agrupadas: dict[Any, dict[str, Any]] = {}
        ordem: list[Any] = []
        for sugestao in pendentes:
            sugestao_id = self._id_sugestao(sugestao)
            if sugestao_id in shown_ids:
                continue
            chave = sugestao.get("chave_agregacao", sugestao_id)
            if chave not in agrupadas:
                agrupadas[chave] = sugestao
                ordem.append(chave)

        selecionadas: list[dict[str, Any]] = [agrupadas[chave] for chave in ordem[:vagas]]
        if not selecionadas:
            return []

        for sugestao in selecionadas:
            shown_ids.append(self._id_sugestao(sugestao))
        self._estado["shown_count"] = int(self._estado.get("shown_count", 0)) + len(selecionadas)
        self._salvar_estado()

        return selecionadas


# Instância global — outros módulos podem depender deste nome.
sugestoes = SugestoesMomento()
