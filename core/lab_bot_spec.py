"""Declarative custom-bot spec ("bots faceis").

A BotSpec is the simple description Alex (or the UI) writes to create a bot
without complication. Validation is fail-closed: unknown roles, unknown
capabilities, bad ids and unknown fields are REJECTED instead of silently
accepted. `create_profile()` turns a valid spec into a real `AgentProfile`
the Lab store already understands.

Defaults follow the engine rule: FREE TIER FIRST (NVIDIA NIM), text only,
one turn. Anything that can change or break things (tools.write/tools.run)
needs an explicit opt-in.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.lab_v1.domain import AgentProfile, Lifecycle, RoleName


class BotSpecError(ValueError):
    """A bot spec did not validate."""


BOT_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")

# Capabilities the runtime actually understands. Anything else is rejected.
KNOWN_CAPABILITIES = frozenset({
    "model.text",
    "model.vision",
    "tools.read",
    "tools.write",
    "tools.web",
    "tools.run",
})

# Capabilities that can change or break things: need an explicit opt-in.
DANGEROUS_CAPABILITIES = frozenset({"tools.write", "tools.run"})

# Free tier first (engine rule). Both exist in core/model_router.py.
DEFAULT_PROVIDER_ID = "nvidia"
DEFAULT_MODEL = "nvidia_glm52"

DEFAULT_CAPABILITIES: tuple[str, ...] = ("model.text",)

MAX_TURNS_LIMIT = 25
MAX_NAME_LEN = 60
MAX_INSTRUCTIONS_LEN = 4000


@dataclass(frozen=True)
class BotSpec:
    id: str
    name: str
    role: RoleName = RoleName.MEMBER
    instructions: str = ""
    provider_id: str = DEFAULT_PROVIDER_ID
    model: str = DEFAULT_MODEL
    capabilities: tuple[str, ...] = DEFAULT_CAPABILITIES
    lifecycle: Lifecycle = Lifecycle.PERMANENT
    reports_to: str | None = None
    max_turns: int = 1
    allow_dangerous: bool = False

    def __post_init__(self) -> None:
        if not BOT_ID_RE.match(self.id or ""):
            raise BotSpecError(
                f"id invalido: {self.id!r} (use minusculas, numeros e hifen)"
            )
        name = (self.name or "").strip()
        if not name or len(name) > MAX_NAME_LEN:
            raise BotSpecError("name precisa de 1 a 60 caracteres")
        if not isinstance(self.role, RoleName):
            raise BotSpecError(
                f"role invalida: {self.role!r} (use um RoleName real, nao invente)"
            )
        if len(self.instructions or "") > MAX_INSTRUCTIONS_LEN:
            raise BotSpecError("instructions passou de 4000 caracteres")
        provider = (self.provider_id or "").strip()
        if not provider or len(provider) > 80:
            raise BotSpecError("provider_id invalido")
        if not (self.model or "").strip() or len(self.model) > 120:
            raise BotSpecError("model invalido")
        caps = tuple(self.capabilities or ())
        if not caps:
            raise BotSpecError("capabilities nao pode ser vazio")
        unknown = [c for c in caps if c not in KNOWN_CAPABILITIES]
        if unknown:
            raise BotSpecError(f"capabilities desconhecidas: {unknown}")
        dangerous = [c for c in caps if c in DANGEROUS_CAPABILITIES]
        if dangerous and not self.allow_dangerous:
            raise BotSpecError(
                f"capabilities perigosas exigem allow_dangerous=True: {dangerous}"
            )
        if not isinstance(self.lifecycle, Lifecycle):
            raise BotSpecError(f"lifecycle invalido: {self.lifecycle!r}")
        if self.reports_to is not None:
            rt = self.reports_to.strip()
            if not rt or len(rt) > MAX_NAME_LEN:
                raise BotSpecError("reports_to invalido")
        if not isinstance(self.max_turns, int) or isinstance(self.max_turns, bool):
            raise BotSpecError("max_turns precisa ser inteiro")
        if not 1 <= self.max_turns <= MAX_TURNS_LIMIT:
            raise BotSpecError(f"max_turns fora de 1..{MAX_TURNS_LIMIT}")


_KNOWN_FIELDS = frozenset({
    "id", "name", "role", "instructions", "provider_id", "model",
    "capabilities", "lifecycle", "reports_to", "max_turns", "allow_dangerous",
})


def from_dict(data: Mapping[str, Any]) -> BotSpec:
    """Build a BotSpec from a plain dict (UI/JSON input). Strict: unknown
    fields are rejected so a typo never becomes a silent default."""
    if not isinstance(data, Mapping):
        raise BotSpecError("spec precisa ser um dicionario")
    unknown = [k for k in data if k not in _KNOWN_FIELDS]
    if unknown:
        raise BotSpecError(f"campos desconhecidos na spec: {unknown}")
    kw: dict[str, Any] = dict(data)
    role = kw.get("role", RoleName.MEMBER)
    if isinstance(role, str):
        try:
            role = RoleName(role)
        except ValueError:
            raise BotSpecError(f"role desconhecida: {role!r}") from None
    kw["role"] = role
    lifecycle = kw.get("lifecycle", Lifecycle.PERMANENT)
    if isinstance(lifecycle, str):
        try:
            lifecycle = Lifecycle(lifecycle)
        except ValueError:
            raise BotSpecError(f"lifecycle desconhecido: {lifecycle!r}") from None
    kw["lifecycle"] = lifecycle
    caps = kw.get("capabilities", DEFAULT_CAPABILITIES)
    if isinstance(caps, list):
        caps = tuple(caps)
    kw["capabilities"] = caps
    try:
        return BotSpec(**kw)
    except TypeError as exc:
        raise BotSpecError(f"spec invalida: {exc}") from None


def to_dict(spec: BotSpec) -> dict[str, Any]:
    """Round-trip: BotSpec -> plain dict -> from_dict."""
    return {
        "id": spec.id,
        "name": spec.name,
        "role": spec.role.value,
        "instructions": spec.instructions,
        "provider_id": spec.provider_id,
        "model": spec.model,
        "capabilities": list(spec.capabilities),
        "lifecycle": spec.lifecycle.value,
        "reports_to": spec.reports_to,
        "max_turns": spec.max_turns,
        "allow_dangerous": spec.allow_dangerous,
    }


def create_profile(spec: BotSpec) -> AgentProfile:
    """Turn a valid BotSpec into a real AgentProfile the Lab store uses."""
    return AgentProfile(
        id=spec.id,
        name=spec.name.strip(),
        provider_id=spec.provider_id.strip(),
        model=spec.model.strip(),
        role=spec.role,
        instructions=spec.instructions,
        capabilities=list(spec.capabilities),
        lifecycle=spec.lifecycle,
        reports_to=spec.reports_to.strip() if spec.reports_to else None,
        max_turns=spec.max_turns,
    )
