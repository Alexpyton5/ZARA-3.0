from __future__ import annotations

import pytest

from core.perception.accessibility_auditor import (
    VisualSample,
    audit_accessibility,
    contrast_ratio,
)
from core.perception.layout_mapper import RawLayoutElement, Rect, map_layout


def _snapshot(*elements: RawLayoutElement, truncated: bool = False):
    snapshot = map_layout(elements, Rect(0, 0, 200, 200))
    if not truncated:
        return snapshot
    return type(snapshot)(viewport=snapshot.viewport, nodes=snapshot.nodes, truncated=True)


def test_complete_sampled_layout_passes() -> None:
    snapshot = _snapshot(
        RawLayoutElement("Button", Rect(10, 10, 32, 32), name="Salvar", automation_id="save"),
        RawLayoutElement("Text", Rect(10, 60, 120, 24), name="Estado pronto", automation_id="status"),
    )

    report = audit_accessibility(
        snapshot,
        samples=(
            VisualSample("id:save", "#FFFFFF", "#000000"),
            VisualSample("id:status", "#FFFFFF", "#000000"),
        ),
    )

    assert report.verdict == "pass"
    assert report.issue_count == 0
    assert report.interactive_nodes == 1
    assert report.contrast_eligible == 2
    assert report.contrast_samples == 2
    assert report.incomplete_reasons == ()


def test_missing_name_and_small_target_fail_with_actionable_evidence() -> None:
    snapshot = _snapshot(RawLayoutElement("Button", Rect(10, 10, 20, 18)))

    report = audit_accessibility(snapshot)

    assert report.verdict == "fail"
    assert {issue.code for issue in report.issues} == {
        "MISSING_ACCESSIBLE_NAME",
        "TARGET_TOO_SMALL",
    }
    size_issue = next(issue for issue in report.issues if issue.code == "TARGET_TOO_SMALL")
    assert size_issue.measured == 18
    assert size_issue.expected == 24


def test_normal_text_fails_45_contrast_while_large_text_uses_30() -> None:
    snapshot = _snapshot(
        RawLayoutElement("Text", Rect(0, 0, 80, 20), name="Normal", automation_id="normal"),
        RawLayoutElement("Text", Rect(0, 30, 80, 30), name="Grande", automation_id="large"),
    )

    report = audit_accessibility(
        snapshot,
        samples=(
            VisualSample("id:normal", "#777777", "#FFFFFF"),
            VisualSample("id:large", "#777777", "#FFFFFF", large_text=True),
        ),
    )

    assert report.verdict == "fail"
    assert [issue.node_key for issue in report.issues] == ["id:normal"]
    assert report.issues[0].code == "LOW_CONTRAST"
    assert report.issues[0].expected == 4.5
    assert report.issues[0].measured == pytest.approx(4.478, abs=0.001)
    assert contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0)


def test_unsampled_or_truncated_layout_is_incomplete_not_false_pass() -> None:
    snapshot = _snapshot(
        RawLayoutElement("Text", Rect(0, 0, 80, 20), name="Sem amostra", automation_id="text"),
        truncated=True,
    )

    report = audit_accessibility(snapshot)

    assert report.verdict == "incomplete"
    assert report.issue_count == 0
    assert report.incomplete_reasons == ("layout_truncated", "contrast_not_fully_sampled")


def test_sensitive_nodes_are_not_leaked_or_counted_as_missing_labels() -> None:
    snapshot = _snapshot(
        RawLayoutElement(
            "Edit",
            Rect(0, 0, 100, 30),
            name="senha secreta",
            automation_id="password",
            is_password=True,
        )
    )

    report = audit_accessibility(snapshot)

    assert report.verdict == "incomplete"
    assert report.issue_count == 0
    assert report.contrast_eligible == 0
    assert report.incomplete_reasons == ("sensitive_nodes_not_audited",)
    assert "senha secreta" not in str(report.to_dict())


def test_samples_fail_closed_when_color_or_target_is_invalid() -> None:
    snapshot = _snapshot(
        RawLayoutElement("Text", Rect(0, 0, 80, 20), name="Texto", automation_id="text")
    )

    with pytest.raises(ValueError, match="cor hexadecimal"):
        VisualSample("id:text", "white", "#000000")
    with pytest.raises(ValueError, match="desconhecido"):
        audit_accessibility(snapshot, samples=(VisualSample("id:other", "#FFFFFF", "#000000"),))
    duplicate = VisualSample("id:text", "#FFFFFF", "#000000")
    with pytest.raises(ValueError, match="duplicada"):
        audit_accessibility(snapshot, samples=(duplicate, duplicate))


def test_issue_limit_is_explicit_and_does_not_hide_failure() -> None:
    snapshot = _snapshot(
        RawLayoutElement("Button", Rect(0, 0, 10, 10)),
        RawLayoutElement("Button", Rect(20, 0, 10, 10)),
    )

    report = audit_accessibility(snapshot, max_issues=1)

    assert report.verdict == "fail"
    assert report.issue_count == 4
    assert len(report.issues) == 1
    assert report.issues_truncated is True
    with pytest.raises(ValueError, match="max_issues"):
        audit_accessibility(snapshot, max_issues=0)
