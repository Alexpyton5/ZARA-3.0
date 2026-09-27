"""Deterministic local tests for agent_inventory_adapter."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

try:
    from .agent_inventory_adapter import DuplicateAgentError, load_agent_inventory
except ImportError:  # Allows direct execution from the project checkout.
    from agent_inventory_adapter import DuplicateAgentError, load_agent_inventory


class AgentInventoryAdapterTests(unittest.TestCase):
    def _write(self, directory: Path, name: str, content: str) -> None:
        (directory / name).write_text(content, encoding="utf-8", newline="\n")

    def test_inventory_is_normalized_sorted_and_json_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self._write(
                directory,
                "zulu.toml",
                '''
name = "  Zulu Analyst  "
description = "Expert in data quality and reporting."
role = "Researcher"
capabilities = [" data quality ", "reporting", "data quality"]
permissions = ["read_only"]
''',
            )
            self._write(
                directory,
                "alpha.toml",
                '''
name = "Alpha Builder"
description = "Builder for small changes."
developer_instructions = "Read-only by default. Never writes outside the declared scope."
''',
            )
            (directory / "ignored.txt").write_text("not an agent", encoding="utf-8")

            inventory = load_agent_inventory(directory)

            self.assertEqual([record["id"] for record in inventory], ["alpha-builder", "zulu-analyst"])
            self.assertEqual(inventory[0]["name"], "Alpha Builder")
            self.assertEqual(inventory[0]["role"], None)
            self.assertEqual(inventory[0]["permissions"], ["read_only"])
            self.assertEqual(inventory[1]["role"], "Researcher")
            self.assertEqual(inventory[1]["capabilities"], ["data quality", "reporting"])
            self.assertEqual(inventory[1]["permissions"], ["read_only"])
            self.assertEqual(inventory[1]["source"], "zulu.toml")
            # The public result must contain only JSON primitives and be stable.
            encoded = json.dumps(inventory, ensure_ascii=False, sort_keys=True)
            self.assertEqual(json.loads(encoded), inventory)

    def test_duplicate_normalized_ids_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self._write(directory, "first.toml", 'name = "Same Agent"\n')
            self._write(directory, "second.toml", 'name = " same-agent "\n')

            with self.assertRaises(DuplicateAgentError) as raised:
                load_agent_inventory(directory)

            self.assertEqual(raised.exception.duplicates, {"same-agent": ("first.toml", "second.toml")})

    def test_explicit_id_wins_and_file_order_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self._write(directory, "z.toml", 'id = "B Agent"\nname = "Later Label"\n')
            self._write(directory, "a.toml", 'id = "a_agent"\nname = "First Label"\n')

            first = load_agent_inventory(directory)
            second = load_agent_inventory(directory)

            self.assertEqual(first, second)
            self.assertEqual([record["id"] for record in first], ["a-agent", "b-agent"])
            self.assertEqual([record["source"] for record in first], ["a.toml", "z.toml"])


if __name__ == "__main__":
    unittest.main()
