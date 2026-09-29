"""Tests for core/lab_bot_spec.py — bots faceis.

Fail-closed proof: unknown roles, unknown capabilities, dangerous tools
without opt-in, bad ids and typos in dict input are all REJECTED.
"""
from __future__ import annotations

import unittest

from core.lab_bot_spec import (
    BotSpec,
    BotSpecError,
    create_profile,
    from_dict,
    to_dict,
)
from core.lab_v1.domain import Lifecycle, RoleName


def good_kwargs(**over):
    kw = dict(id="bot-lima", name="Lima", role=RoleName.RESEARCHER,
              instructions="Pesquisa na web e resume em portugues simples.")
    kw.update(over)
    return kw


class TestValidSpec(unittest.TestCase):
    def test_maps_to_real_agent_profile(self):
        spec = BotSpec(**good_kwargs())
        profile = create_profile(spec)
        self.assertEqual(profile.id, "bot-lima")
        self.assertEqual(profile.name, "Lima")
        self.assertEqual(profile.role, RoleName.RESEARCHER)
        self.assertEqual(profile.instructions,
                         "Pesquisa na web e resume em portugues simples.")
        self.assertEqual(profile.capabilities, ["model.text"])
        self.assertEqual(profile.max_turns, 1)
        self.assertFalse(profile.archived)

    def test_defaults_are_free_tier(self):
        spec = BotSpec(id="bot-x", name="X")
        self.assertEqual(spec.provider_id, "nvidia")
        self.assertEqual(spec.model, "nvidia_glm52")
        self.assertEqual(spec.capabilities, ("model.text",))
        self.assertEqual(spec.role, RoleName.MEMBER)
        self.assertEqual(spec.lifecycle, Lifecycle.PERMANENT)
        self.assertIsNone(spec.reports_to)


class TestFailClosed(unittest.TestCase):
    def test_unknown_role_string_rejected(self):
        with self.assertRaises(BotSpecError):
            from_dict({"id": "bot-x", "name": "X", "role": "CTO"})

    def test_role_must_be_real_rolename(self):
        with self.assertRaises(BotSpecError):
            BotSpec(id="bot-x", name="X", role="RESEARCHER")  # str, not RoleName

    def test_unknown_capability_rejected(self):
        with self.assertRaises(BotSpecError):
            BotSpec(**good_kwargs(capabilities=("model.telepathy",)))

    def test_empty_capabilities_rejected(self):
        with self.assertRaises(BotSpecError):
            BotSpec(**good_kwargs(capabilities=()))

    def test_dangerous_capability_needs_opt_in(self):
        with self.assertRaises(BotSpecError):
            BotSpec(**good_kwargs(capabilities=("model.text", "tools.write")))
        ok = BotSpec(**good_kwargs(capabilities=("model.text", "tools.write"),
                                   allow_dangerous=True))
        self.assertIn("tools.write", ok.capabilities)

    def test_bad_ids_rejected(self):
        for bad in ("Bot Lima", "BOT", "bot_lima", "-bot", "bot-", "", "a" * 41):
            with self.assertRaises(BotSpecError, msg=bad):
                BotSpec(id=bad, name="X")

    def test_empty_name_rejected(self):
        with self.assertRaises(BotSpecError):
            BotSpec(id="bot-x", name="   ")

    def test_unknown_field_rejected_no_silent_typo(self):
        with self.assertRaises(BotSpecError):
            from_dict({"id": "bot-x", "name": "X", "capabilites": ["model.text"]})

    def test_max_turns_bounds(self):
        with self.assertRaises(BotSpecError):
            BotSpec(**good_kwargs(max_turns=0))
        with self.assertRaises(BotSpecError):
            BotSpec(**good_kwargs(max_turns=26))
        with self.assertRaises(BotSpecError):
            BotSpec(**good_kwargs(max_turns=True))


class TestDictRoundTrip(unittest.TestCase):
    def test_round_trip(self):
        spec = BotSpec(**good_kwargs(capabilities=("model.text", "tools.web"),
                                     reports_to="CEO", max_turns=3))
        back = from_dict(to_dict(spec))
        self.assertEqual(to_dict(back), to_dict(spec))

    def test_from_dict_parses_role_string(self):
        spec = from_dict({"id": "bot-x", "name": "X", "role": "TESTER"})
        self.assertEqual(spec.role, RoleName.TESTER)

    def test_not_a_dict_rejected(self):
        with self.assertRaises(BotSpecError):
            from_dict(["bot-x"])


if __name__ == "__main__":
    unittest.main()
