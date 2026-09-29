"""BotSpec store ("bots faceis", peca 2): ligar a spec declarativa ao Lab.

Duas coisas simples:
- BotStore: guarda cada BotSpec valida como um JSON `<id>.json` num diretorio
  (padrao: <data_dir>/lab/bots, ao lado do banco do Lab). Escrita atomica
  (tmp + replace), leitura estrita via from_dict — arquivo corrompido ou com
  campo desconhecido vira erro, nunca default silencioso.
- register(lab_store, spec): transforma a spec num AgentProfile de verdade e
  salva no LabStore (save_agent faz upsert pelo id). O caminho inverso
  (spec_from_agent) recupera a spec a partir do AgentProfile do banco, para a
  UI editar depois sem re-digitar nada.

Fail-closed do inicio ao fim: nada aqui inventa valor quando falta dado.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.lab_v1.domain import AgentProfile
from core.lab_v1.store import LabStore
from core.paths import data_dir

from core.lab_bot_spec import (
    BotSpec,
    BotSpecError,
    create_profile,
    from_dict,
    to_dict,
)

# Capabilities que mudam ou quebram coisas: a spec que as tem precisa do
# opt-in, e o caminho inverso marca o opt-in sozinho a partir delas.
_DANGEROUS = frozenset({"tools.write", "tools.run"})


class BotStoreError(Exception):
    """O store de specs nao conseguiu cumprir o pedido."""


def default_bots_dir() -> Path:
    """Onde as specs moram por padrao: ao lado do banco do Lab."""
    return data_dir() / "lab" / "bots"


@dataclass
class BotStore:
    """Um diretorio de specs: um `<id>.json` por bot."""

    dir: Path | None = None

    def __post_init__(self) -> None:
        d = Path(self.dir) if self.dir is not None else default_bots_dir()
        d.mkdir(parents=True, exist_ok=True)
        self.dir = d

    def _path(self, bot_id: str) -> Path:
        return self.dir / f"{bot_id}.json"

    def save(self, spec: BotSpec) -> Path:
        """Guarda a spec (ja validada pelo proprio BotSpec). Mesmo id =
        sobrescreve. Retorna o caminho do arquivo."""
        payload: dict[str, Any] = to_dict(spec)
        payload["_saved_at"] = datetime.now(timezone.utc).isoformat()
        target = self._path(spec.id)
        fd, tmp = tempfile.mkstemp(
            dir=str(self.dir), prefix=spec.id + ".", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, target)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return target

    def load(self, bot_id: str) -> BotSpec:
        """Le a spec do disco. Inexistente ou corrompida = erro."""
        path = self._path(bot_id)
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise BotStoreError(f"bot nao existe no store: {bot_id!r}") from None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BotStoreError(f"arquivo corrompido: {path.name} ({exc})") from None
        if not isinstance(data, dict):
            raise BotStoreError(f"arquivo corrompido: {path.name} (nao e objeto)")
        data.pop("_saved_at", None)
        try:
            return from_dict(data)
        except BotSpecError as exc:
            raise BotStoreError(f"spec invalida em {path.name}: {exc}") from None

    def exists(self, bot_id: str) -> bool:
        return self._path(bot_id).is_file()

    def list(self) -> list[BotSpec]:
        """Todas as specs, ordenadas por id. Arquivo invalido = erro alto."""
        specs = []
        for path in sorted(self.dir.glob("*.json")):
            specs.append(self.load(path.stem))
        return specs

    def delete(self, bot_id: str) -> None:
        """Apaga a spec. Inexistente = erro (nao finge que apagou)."""
        try:
            self._path(bot_id).unlink()
        except FileNotFoundError:
            raise BotStoreError(f"bot nao existe no store: {bot_id!r}") from None


def register(lab_store: LabStore, spec: BotSpec) -> AgentProfile:
    """Liga a spec ao Lab: AgentProfile real salvo no banco (upsert por id)."""
    profile = create_profile(spec)
    lab_store.save_agent(profile)
    return profile


def register_by_id(
    bot_store: BotStore, lab_store: LabStore, bot_id: str
) -> AgentProfile:
    """Atalho: carrega a spec do BotStore e registra no Lab."""
    return register(lab_store, bot_store.load(bot_id))


def spec_from_agent(agent: AgentProfile) -> BotSpec:
    """Caminho inverso: AgentProfile do banco -> BotSpec editavel na UI.

    Capabilities fora do vocabulario conhecido sao rejeitadas (fail-closed),
    e o opt-in de capabilities perigosas e derivado das proprias capabilities.
    """
    data: dict[str, Any] = {
        "id": agent.id,
        "name": agent.name,
        "role": agent.role,
        "instructions": agent.instructions or "",
        "provider_id": agent.provider_id,
        "model": agent.model,
        "capabilities": list(agent.capabilities or ()),
        "lifecycle": agent.lifecycle,
        "max_turns": agent.max_turns if agent.max_turns else 1,
    }
    if agent.reports_to:
        data["reports_to"] = agent.reports_to
    data["allow_dangerous"] = any(c in _DANGEROUS for c in data["capabilities"])
    return from_dict(data)
