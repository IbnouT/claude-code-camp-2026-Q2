"""Deterministic campaign phase selection and its volatile delivery."""

import json
import unittest

from boukensha.campaign import CampaignController


def controller(**settings) -> CampaignController:
    settings.setdefault("target", "minotaur")
    return CampaignController(lambda: None, settings)


def readiness(**overrides) -> dict:
    base = {
        "target": "minotaur",
        "sighted_places": [],
        "sighted_titles": [],
        "hit": 40,
        "max_hit": 46,
        "move": 80,
        "max_move": 84,
        "level": 3,
        "gold": 0,
        "rooms_known": 30,
        "frontier_remaining": 12,
    }
    base.update(overrides)
    return base


class TestPhaseSelection(unittest.TestCase):
    def test_low_health_always_survives_first(self):
        phase, reason = controller().phase(
            readiness(hit=10, sighted_places=["place:x"])
        )
        self.assertEqual("survive", phase)
        self.assertIn("21%", reason)

    def test_unsighted_target_locates(self):
        phase, reason = controller().phase(readiness())
        self.assertEqual("locate", phase)
        self.assertIn("12 rooms", reason)

    def test_sighted_but_wounded_prepares(self):
        phase, _ = controller().phase(
            readiness(hit=30, sighted_places=["place:x"])
        )
        self.assertEqual("prepare", phase)

    def test_healthy_and_sighted_engages_with_the_place_named(self):
        phase, reason = controller().phase(readiness(
            hit=46,
            sighted_places=["place:x"],
            sighted_titles=["The Maze Entrance"],
        ))
        self.assertEqual("engage", phase)
        self.assertIn("The Maze Entrance", reason)

    def test_unknown_vitals_never_block_locating(self):
        phase, _ = controller().phase(
            readiness(hit=None, max_hit=None)
        )
        self.assertEqual("locate", phase)


class TestLine(unittest.TestCase):
    def test_line_renders_phase_from_fetched_readiness(self):
        payload = json.dumps(readiness())
        campaign = CampaignController(
            lambda: payload, {"target": "minotaur"}
        )
        line = campaign.line()
        self.assertTrue(line.startswith("campaign: locate"))

    def test_line_is_none_without_target_or_readiness(self):
        no_target = CampaignController(lambda: "{}", {})
        self.assertIsNone(no_target.line())
        no_data = CampaignController(lambda: None, {"target": "minotaur"})
        self.assertIsNone(no_data.line())
        malformed = CampaignController(
            lambda: "not json", {"target": "minotaur"}
        )
        self.assertIsNone(malformed.line())


if __name__ == "__main__":
    unittest.main()
