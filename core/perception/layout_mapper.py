"""Mapa semântico e comparável de layouts de interface dinâmicos.

O módulo é deliberadamente puro: não captura tela, não usa UI Automation e não
executa cliques. Adaptadores de percepção entregam elementos já observados; aqui
eles são filtrados, normalizados e comparados sem coordenadas fixas.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

_MAX_LABEL_LENGTH = 120
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _clean_text(value: object, *, limit: int = _MAX_LABEL_LENGTH) -> str:
    text = "" if value is None else str(value)
    text = " ".join(part for part in text.split() if part)
    return "".join(char for char in text if char.isprintable())[:limit]


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return "-".join(_TOKEN_RE.findall(normalized.lower()))


def _tokens(value: str) -> set[str]:
    return set(_TOKEN_RE.findall(_slug(value).replace("-", " ")))


@dataclass(frozen=True, slots=True)
class Rect:
    left: float
    top: float
    width: float
    height: float

    def __post_init__(self) -> None:
        values = (self.left, self.top, self.width, self.height)
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
            raise ValueError("retângulo precisa conter números")
        if any(not math.isfinite(float(value)) for value in values):
            raise ValueError("retângulo precisa conter valores finitos")
        if self.width < 0 or self.height < 0:
            raise ValueError("largura e altura não podem ser negativas")

    @property
    def right(self) -> float:
        return self.left + self.width

    @property
    def bottom(self) -> float:
        return self.top + self.height

    @property
    def center(self) -> tuple[float, float]:
        return self.left + self.width / 2, self.top + self.height / 2

    def intersection(self, other: Rect) -> Rect | None:
        left = max(self.left, other.left)
        top = max(self.top, other.top)
        right = min(self.right, other.right)
        bottom = min(self.bottom, other.bottom)
        if right <= left or bottom <= top:
            return None
        return Rect(left, top, right - left, bottom - top)

    def normalized_to(self, viewport: Rect) -> tuple[float, float, float, float]:
        if viewport.width <= 0 or viewport.height <= 0:
            raise ValueError("viewport precisa ter área positiva")
        return (
            round((self.left - viewport.left) / viewport.width, 6),
            round((self.top - viewport.top) / viewport.height, 6),
            round(self.width / viewport.width, 6),
            round(self.height / viewport.height, 6),
        )


@dataclass(frozen=True, slots=True)
class RawLayoutElement:
    control_type: str
    bounds: Rect
    name: str = ""
    automation_id: str = ""
    enabled: bool = True
    offscreen: bool = False
    is_password: bool = False


@dataclass(frozen=True, slots=True)
class LayoutNode:
    key: str
    key_source: Literal["automation_id", "label", "position"]
    role: str
    label: str
    automation_id: str
    bounds: Rect
    normalized_bounds: tuple[float, float, float, float]
    region: str
    enabled: bool
    sensitive: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "key_source": self.key_source,
            "role": self.role,
            "label": self.label,
            "automation_id": self.automation_id,
            "bounds": {
                "left": self.bounds.left,
                "top": self.bounds.top,
                "width": self.bounds.width,
                "height": self.bounds.height,
            },
            "normalized_bounds": list(self.normalized_bounds),
            "region": self.region,
            "enabled": self.enabled,
            "sensitive": self.sensitive,
        }


@dataclass(frozen=True, slots=True)
class LayoutSnapshot:
    viewport: Rect
    nodes: tuple[LayoutNode, ...]
    truncated: bool = False

    @property
    def by_key(self) -> dict[str, LayoutNode]:
        return {node.key: node for node in self.nodes}

    def to_dict(self) -> dict[str, object]:
        return {
            "viewport": {
                "left": self.viewport.left,
                "top": self.viewport.top,
                "width": self.viewport.width,
                "height": self.viewport.height,
            },
            "nodes": [node.to_dict() for node in self.nodes],
            "count": len(self.nodes),
            "truncated": self.truncated,
        }


ChangeKind = Literal["added", "removed", "moved", "resized", "changed"]


@dataclass(frozen=True, slots=True)
class LayoutChange:
    kind: ChangeKind
    key: str
    before: LayoutNode | None
    after: LayoutNode | None

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "key": self.key,
            "before": None if self.before is None else self.before.to_dict(),
            "after": None if self.after is None else self.after.to_dict(),
        }


def _region(bounds: tuple[float, float, float, float]) -> str:
    left, top, width, height = bounds
    x = left + width / 2
    y = top + height / 2
    horizontal = "left" if x < 1 / 3 else "right" if x > 2 / 3 else "center"
    vertical = "top" if y < 1 / 3 else "bottom" if y > 2 / 3 else "middle"
    return f"{vertical}-{horizontal}"


def _base_key(element: RawLayoutElement, normalized: tuple[float, float, float, float]) -> tuple[str, str]:
    automation_id = _slug(_clean_text(element.automation_id))
    role = _slug(_clean_text(element.control_type)) or "unknown"
    label = _slug(_clean_text(element.name))
    if automation_id:
        return f"id:{automation_id}", "automation_id"
    if label:
        return f"role:{role}|label:{label}", "label"
    x, y, width, height = normalized
    bucket = (round((x + width / 2) * 10), round((y + height / 2) * 10))
    return f"role:{role}|cell:{bucket[0]}:{bucket[1]}", "position"


def map_layout(
    elements: Iterable[RawLayoutElement],
    viewport: Rect,
    *,
    max_nodes: int = 200,
) -> LayoutSnapshot:
    """Cria um snapshot determinístico, limitado e seguro do layout observado."""
    if isinstance(max_nodes, bool) or not isinstance(max_nodes, int) or max_nodes < 1:
        raise ValueError("max_nodes precisa ser inteiro positivo")
    if viewport.width <= 0 or viewport.height <= 0:
        raise ValueError("viewport precisa ter área positiva")

    visible: list[tuple[RawLayoutElement, Rect]] = []
    for element in elements:
        if not isinstance(element, RawLayoutElement):
            raise TypeError("elements precisa conter RawLayoutElement")
        if element.offscreen or element.bounds.width <= 0 or element.bounds.height <= 0:
            continue
        clipped = element.bounds.intersection(viewport)
        if clipped is None or clipped.width * clipped.height < 1:
            continue
        visible.append((element, clipped))

    visible.sort(
        key=lambda item: (
            round(item[1].top, 3),
            round(item[1].left, 3),
            _slug(item[0].control_type),
            _slug(item[0].name),
            _slug(item[0].automation_id),
        )
    )
    truncated = len(visible) > max_nodes
    visible = visible[:max_nodes]

    occurrences: dict[str, int] = {}
    nodes: list[LayoutNode] = []
    for element, clipped in visible:
        normalized = clipped.normalized_to(viewport)
        base_key, source = _base_key(element, normalized)
        occurrences[base_key] = occurrences.get(base_key, 0) + 1
        suffix = "" if occurrences[base_key] == 1 else f"#{occurrences[base_key]}"
        sensitive = bool(element.is_password)
        nodes.append(
            LayoutNode(
                key=base_key + suffix,
                key_source=source,  # type: ignore[arg-type]
                role=_clean_text(element.control_type, limit=48).lower() or "unknown",
                label="" if sensitive else _clean_text(element.name),
                automation_id=_clean_text(element.automation_id, limit=80),
                bounds=clipped,
                normalized_bounds=normalized,
                region=_region(normalized),
                enabled=bool(element.enabled),
                sensitive=sensitive,
            )
        )
    return LayoutSnapshot(viewport=viewport, nodes=tuple(nodes), truncated=truncated)


def diff_layout(
    before: LayoutSnapshot,
    after: LayoutSnapshot,
    *,
    movement_threshold: float = 0.02,
    size_threshold: float = 0.02,
) -> tuple[LayoutChange, ...]:
    """Compara snapshots em coordenadas normalizadas, tolerando troca de resolução."""
    for value, name in ((movement_threshold, "movement_threshold"), (size_threshold, "size_threshold")):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise ValueError(f"{name} precisa estar entre 0 e 1")

    old = before.by_key
    new = after.by_key
    changes: list[LayoutChange] = []
    for key in sorted(old.keys() - new.keys()):
        changes.append(LayoutChange("removed", key, old[key], None))
    for key in sorted(new.keys() - old.keys()):
        changes.append(LayoutChange("added", key, None, new[key]))
    for key in sorted(old.keys() & new.keys()):
        previous = old[key]
        current = new[key]
        px, py, pw, ph = previous.normalized_bounds
        cx, cy, cw, ch = current.normalized_bounds
        if max(abs(px - cx), abs(py - cy)) > movement_threshold:
            changes.append(LayoutChange("moved", key, previous, current))
        if max(abs(pw - cw), abs(ph - ch)) > size_threshold:
            changes.append(LayoutChange("resized", key, previous, current))
        if (
            previous.label != current.label
            or previous.role != current.role
            or previous.enabled != current.enabled
            or previous.sensitive != current.sensitive
        ):
            changes.append(LayoutChange("changed", key, previous, current))
    return tuple(changes)


def find_targets(
    snapshot: LayoutSnapshot,
    query: str,
    *,
    roles: Iterable[str] = (),
    limit: int = 10,
) -> tuple[tuple[float, LayoutNode], ...]:
    """Encontra alvos sem coordenada fixa; nunca retorna campos sensíveis."""
    clean_query = _clean_text(query)
    query_slug = _slug(clean_query)
    query_tokens = _tokens(clean_query)
    if not query_slug:
        return ()
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit precisa ser inteiro positivo")
    accepted_roles = {_slug(role) for role in roles if _slug(role)}

    matches: list[tuple[float, LayoutNode]] = []
    for node in snapshot.nodes:
        if node.sensitive:
            continue
        role_slug = _slug(node.role)
        if accepted_roles and role_slug not in accepted_roles:
            continue
        candidates = (_slug(node.label), _slug(node.automation_id), role_slug)
        score = 0.0
        for candidate in candidates:
            if not candidate:
                continue
            if candidate == query_slug:
                score = max(score, 1.0)
            elif query_slug in candidate:
                score = max(score, 0.85)
            else:
                candidate_tokens = _tokens(candidate)
                if query_tokens and candidate_tokens:
                    score = max(score, len(query_tokens & candidate_tokens) / len(query_tokens) * 0.7)
        if score > 0:
            matches.append((round(score, 3), node))
    matches.sort(key=lambda item: (-item[0], item[1].key))
    return tuple(matches[:limit])
