from __future__ import annotations

import unittest

from core.perception.layout_mapper import (
    RawLayoutElement,
    Rect,
    diff_layout,
    find_targets,
    map_layout,
)


class LayoutMapperTests(unittest.TestCase):
    def test_filters_invisible_elements_clips_bounds_and_redacts_password(self) -> None:
        viewport = Rect(100, 50, 1000, 500)
        snapshot = map_layout(
            [
                RawLayoutElement("Button", Rect(0, 0, 10, 10), name="fora"),
                RawLayoutElement("Text", Rect(150, 70, 120, 20), name="oculto", offscreen=True),
                RawLayoutElement(
                    "Edit",
                    Rect(90, 40, 200, 60),
                    name="segredo que não pode sair",
                    automation_id="password-field",
                    is_password=True,
                ),
            ],
            viewport,
        )

        self.assertEqual(len(snapshot.nodes), 1)
        node = snapshot.nodes[0]
        self.assertEqual(node.label, "")
        self.assertTrue(node.sensitive)
        self.assertEqual(node.bounds, Rect(100, 50, 190, 50))
        self.assertEqual(node.normalized_bounds, (0.0, 0.0, 0.19, 0.1))

    def test_stable_automation_id_tracks_movement_across_layouts(self) -> None:
        viewport = Rect(0, 0, 1000, 1000)
        before = map_layout(
            [RawLayoutElement("Button", Rect(100, 100, 100, 50), name="Salvar", automation_id="save")],
            viewport,
        )
        after = map_layout(
            [RawLayoutElement("Button", Rect(700, 700, 100, 50), name="Salvar", automation_id="save")],
            viewport,
        )

        self.assertEqual(before.nodes[0].key, "id:save")
        self.assertEqual(after.nodes[0].key, "id:save")
        self.assertEqual([change.kind for change in diff_layout(before, after)], ["moved"])

    def test_diff_detects_add_remove_resize_and_state_change(self) -> None:
        viewport = Rect(0, 0, 100, 100)
        before = map_layout(
            [
                RawLayoutElement("Button", Rect(0, 0, 10, 10), name="Antigo", automation_id="gone"),
                RawLayoutElement("Edit", Rect(10, 20, 20, 10), name="Busca", automation_id="search"),
            ],
            viewport,
        )
        after = map_layout(
            [
                RawLayoutElement(
                    "Edit", Rect(10, 20, 50, 10), name="Pesquisar", automation_id="search", enabled=False
                ),
                RawLayoutElement("Button", Rect(80, 80, 10, 10), name="Novo", automation_id="new"),
            ],
            viewport,
        )

        kinds = [change.kind for change in diff_layout(before, after)]
        self.assertEqual(kinds, ["removed", "added", "resized", "changed"])

    def test_duplicate_labels_receive_deterministic_suffixes(self) -> None:
        viewport = Rect(0, 0, 500, 500)
        elements = [
            RawLayoutElement("Button", Rect(50, 100, 50, 20), name="OK"),
            RawLayoutElement("Button", Rect(50, 20, 50, 20), name="OK"),
        ]

        snapshot = map_layout(reversed(elements), viewport)

        self.assertEqual(
            [node.key for node in snapshot.nodes],
            ["role:button|label:ok", "role:button|label:ok#2"],
        )
        self.assertEqual([node.bounds.top for node in snapshot.nodes], [20, 100])

    def test_find_targets_uses_semantics_role_filter_and_hides_sensitive_nodes(self) -> None:
        snapshot = map_layout(
            [
                RawLayoutElement("Button", Rect(0, 0, 20, 10), name="Salvar documento", automation_id="save-doc"),
                RawLayoutElement("Text", Rect(0, 20, 20, 10), name="Salvar documento"),
                RawLayoutElement("Edit", Rect(0, 40, 20, 10), name="Salvar", is_password=True),
            ],
            Rect(0, 0, 100, 100),
        )

        matches = find_targets(snapshot, "salvar", roles=("button",))

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0][1].automation_id, "save-doc")
        self.assertGreaterEqual(matches[0][0], 0.7)

    def test_limit_is_deterministic_and_reports_truncation(self) -> None:
        elements = [
            RawLayoutElement("Button", Rect(0, top, 10, 5), name=f"B{top}")
            for top in (30, 10, 20)
        ]

        snapshot = map_layout(elements, Rect(0, 0, 100, 100), max_nodes=2)

        self.assertTrue(snapshot.truncated)
        self.assertEqual([node.bounds.top for node in snapshot.nodes], [10, 20])

    def test_invalid_limits_and_viewport_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "max_nodes"):
            map_layout([], Rect(0, 0, 10, 10), max_nodes=0)
        with self.assertRaisesRegex(ValueError, "área positiva"):
            map_layout([], Rect(0, 0, 0, 10))
        with self.assertRaisesRegex(ValueError, "limit"):
            find_targets(map_layout([], Rect(0, 0, 10, 10)), "x", limit=0)


if __name__ == "__main__":
    unittest.main()
