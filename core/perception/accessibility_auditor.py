"""Auditoria pura e limitada de acessibilidade visual para layouts observados.

O módulo reutiliza ``layout_mapper`` e não captura tela nem executa ações. Ele
combina semântica observada (nome acessível e tamanho de alvo) com amostras de
cores fornecidas por um adaptador. Ausência de amostra nunca vira aprovação:
o relatório fica ``incomplete`` em vez de produzir falso sucesso.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from core.perception.layout_mapper import LayoutSnapshot

_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")
_MIN_TARGET_SIZE = 24.0
_INTERACTIVE_ROLES = frozenset(
    {
        "button",
        "check box",
        "checkbox",
        "combo box",
        "combobox",
        "edit",
        "hyperlink",
        "link",
        "list item",
        "menu item",
        "radio button",
        "slider",
        "spinner",
        "tab",
        "tab item",
        "tree item",
    }
)

Severity = Literal["critical", "serious", "moderate"]
Verdict = Literal["pass", "fail", "incomplete"]


def _validate_color(value: str) -> str:
    if not isinstance(value, str) or _HEX_COLOR.fullmatch(value) is None:
        raise ValueError("cor hexadecimal precisa usar o formato #RRGGBB")
    return value.upper()


def _relative_luminance(color: str) -> float:
    normalized = _validate_color(color)
    channels = [int(normalized[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(foreground: str, background: str) -> float:
    """Calcula a razão de contraste WCAG entre duas cores ``#RRGGBB``."""
    first = _relative_luminance(foreground)
    second = _relative_luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


@dataclass(frozen=True, slots=True)
class VisualSample:
    """Amostra de primeiro plano/fundo associada a uma chave do layout."""

    node_key: str
    foreground: str
    background: str
    large_text: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.node_key, str) or not self.node_key.strip():
            raise ValueError("node_key não pode ser vazio")
        object.__setattr__(self, "node_key", self.node_key.strip())
        object.__setattr__(self, "foreground", _validate_color(self.foreground))
        object.__setattr__(self, "background", _validate_color(self.background))
        if not isinstance(self.large_text, bool):
            raise TypeError("large_text precisa ser booleano")


@dataclass(frozen=True, slots=True)
class AccessibilityIssue:
    code: str
    severity: Severity
    node_key: str
    message: str
    measured: float | None = None
    expected: float | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity,
            "node_key": self.node_key,
            "message": self.message,
            "measured": self.measured,
            "expected": self.expected,
        }


@dataclass(frozen=True, slots=True)
class AccessibilityReport:
    verdict: Verdict
    issues: tuple[AccessibilityIssue, ...]
    issue_count: int
    nodes_audited: int
    interactive_nodes: int
    contrast_eligible: int
    contrast_samples: int
    incomplete_reasons: tuple[str, ...]
    issues_truncated: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "verdict": self.verdict,
            "issues": [issue.to_dict() for issue in self.issues],
            "issue_count": self.issue_count,
            "nodes_audited": self.nodes_audited,
            "interactive_nodes": self.interactive_nodes,
            "contrast_eligible": self.contrast_eligible,
            "contrast_samples": self.contrast_samples,
            "incomplete_reasons": list(self.incomplete_reasons),
            "issues_truncated": self.issues_truncated,
        }


def _normalize_role(role: str) -> str:
    return " ".join(role.strip().lower().replace("_", " ").replace("-", " ").split())


def audit_accessibility(
    snapshot: LayoutSnapshot,
    *,
    samples: tuple[VisualSample, ...] = (),
    max_issues: int = 100,
) -> AccessibilityReport:
    """Audita nomes, alvos e contraste sem afirmar cobertura que não existe.

    Tamanho mínimo de alvo usa WCAG 2.2 AA (24x24). Contraste usa 4,5:1 para
    texto normal e 3:1 para texto grande. ``samples`` deve cobrir cada nó com
    rótulo visível para um veredito completo.
    """
    if not isinstance(snapshot, LayoutSnapshot):
        raise TypeError("snapshot precisa ser LayoutSnapshot")
    if isinstance(max_issues, bool) or not isinstance(max_issues, int) or max_issues < 1:
        raise ValueError("max_issues precisa ser inteiro positivo")
    if not isinstance(samples, tuple) or any(not isinstance(sample, VisualSample) for sample in samples):
        raise TypeError("samples precisa ser tuple de VisualSample")

    nodes_by_key = {node.key: node for node in snapshot.nodes}
    if len(nodes_by_key) != len(snapshot.nodes):
        raise ValueError("snapshot contém chaves duplicadas")

    samples_by_key: dict[str, VisualSample] = {}
    for sample in samples:
        if sample.node_key not in nodes_by_key:
            raise ValueError(f"alvo de amostra desconhecido: {sample.node_key}")
        if sample.node_key in samples_by_key:
            raise ValueError(f"amostra duplicada para: {sample.node_key}")
        samples_by_key[sample.node_key] = sample

    issues: list[AccessibilityIssue] = []
    interactive_nodes = 0
    sensitive_nodes = 0
    eligible_keys: set[str] = set()

    for node in snapshot.nodes:
        if node.sensitive:
            sensitive_nodes += 1
            continue
        if node.label:
            eligible_keys.add(node.key)
        role = _normalize_role(node.role)
        if not node.enabled or role not in _INTERACTIVE_ROLES:
            continue
        interactive_nodes += 1
        if not node.label:
            issues.append(
                AccessibilityIssue(
                    code="MISSING_ACCESSIBLE_NAME",
                    severity="serious",
                    node_key=node.key,
                    message="Controle interativo sem nome acessível.",
                )
            )
        smallest_side = min(node.bounds.width, node.bounds.height)
        if smallest_side < _MIN_TARGET_SIZE:
            issues.append(
                AccessibilityIssue(
                    code="TARGET_TOO_SMALL",
                    severity="serious",
                    node_key=node.key,
                    message="Alvo interativo menor que 24x24.",
                    measured=smallest_side,
                    expected=_MIN_TARGET_SIZE,
                )
            )

    for sample in samples:
        ratio = contrast_ratio(sample.foreground, sample.background)
        minimum = 3.0 if sample.large_text else 4.5
        if ratio < minimum:
            issues.append(
                AccessibilityIssue(
                    code="LOW_CONTRAST",
                    severity="serious",
                    node_key=sample.node_key,
                    message="Contraste visual abaixo do mínimo WCAG AA.",
                    measured=round(ratio, 3),
                    expected=minimum,
                )
            )

    incomplete_reasons: list[str] = []
    if snapshot.truncated:
        incomplete_reasons.append("layout_truncated")
    if eligible_keys - samples_by_key.keys():
        incomplete_reasons.append("contrast_not_fully_sampled")
    if sensitive_nodes:
        incomplete_reasons.append("sensitive_nodes_not_audited")

    issue_count = len(issues)
    issues_truncated = issue_count > max_issues
    if issue_count:
        verdict: Verdict = "fail"
    elif incomplete_reasons:
        verdict = "incomplete"
    else:
        verdict = "pass"

    return AccessibilityReport(
        verdict=verdict,
        issues=tuple(issues[:max_issues]),
        issue_count=issue_count,
        nodes_audited=len(snapshot.nodes) - sensitive_nodes,
        interactive_nodes=interactive_nodes,
        contrast_eligible=len(eligible_keys),
        contrast_samples=len(samples),
        incomplete_reasons=tuple(incomplete_reasons),
        issues_truncated=issues_truncated,
    )
