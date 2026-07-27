"""Turn endings are always stated: a ceiling must never look like a choice."""

import unittest

from boukensha.journey import Presenter


class TestStopReasonSurfaced(unittest.TestCase):
    def test_a_token_limit_names_itself_with_the_numbers(self):
        # "token limit", not "spend limit": with a separate cost ceiling, spend
        # means money, so the volume ceiling has to say what it actually caps.
        p = Presenter()
        p.on_event({"phase": "limit_reached", "kind": "max_tokens",
                    "n": 62357, "max": 60000})
        cards = p.on_event({"phase": "turn_end", "reason": "max_tokens",
                            "iterations": 11})
        self.assertEqual("stopped: token limit 62357/60000", p.last_stop)
        self.assertEqual(1, len(cards))
        self.assertEqual("stop", cards[0].kind)
        self.assertIn("11 step(s)", cards[0].body)
        # The message names the way out, not only the cause.
        self.assertIn("/continue", cards[0].body)
        self.assertIn("/limits turn_tokens", cards[0].body)

    def test_a_step_limit_names_itself(self):
        p = Presenter()
        p.on_event({"phase": "limit_reached", "kind": "max_iterations",
                    "n": 25, "max": 25})
        p.on_event({"phase": "turn_end", "reason": "max_iterations",
                    "iterations": 25})
        self.assertEqual("stopped: step limit 25/25", p.last_stop)

    def test_a_completed_turn_needs_no_card(self):
        p = Presenter()
        cards = p.on_event({"phase": "turn_end", "reason": "completed",
                            "iterations": 3})
        self.assertEqual([], cards)
        self.assertEqual("completed", p.last_stop)

    def test_a_stale_limit_does_not_leak_into_the_next_turn(self):
        p = Presenter()
        p.on_event({"phase": "limit_reached", "kind": "max_tokens",
                    "n": 62357, "max": 60000})
        p.on_event({"phase": "turn_end", "reason": "max_tokens", "iterations": 11})
        p.on_event({"phase": "turn_end", "reason": "completed", "iterations": 2})
        self.assertEqual("completed", p.last_stop)
