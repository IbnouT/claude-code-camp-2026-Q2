"""The top-level agent: config block (decision A4a), resolved layered.

A per-task value wins, else the agent-wide default, else the code default. This
adopts the reference's step-12 agent: block while keeping the task-level
overrides our earlier steps have always had.
"""

import os
import tempfile
import unittest
from pathlib import Path

from boukensha.config import Config
from boukensha.tasks import Player


class TestLayeredResolution(unittest.TestCase):
    def test_task_value_wins_over_agent_default(self):
        self.assertEqual(
            5000, Player.max_turn_tokens({"max_turn_tokens": 5000}, default=40000))

    def test_agent_default_used_when_task_unset(self):
        self.assertEqual(40000, Player.max_turn_tokens({}, default=40000))

    def test_code_default_when_neither_set(self):
        self.assertEqual(60000, Player.max_turn_tokens({}, default=None))

    def test_compaction_threshold_layers_too(self):
        self.assertEqual(0.5, Player.compaction_threshold({}, default=0.5))
        self.assertEqual(0.85, Player.compaction_threshold({}, default=None))


class TestConfigAgentBlock(unittest.TestCase):
    def test_agent_setting_reads_the_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = Path(tmp) / ".boukensha"
            cfg_dir.mkdir()
            (cfg_dir / "settings.yaml").write_text(
                "agent:\n"
                "  max_turn_tokens: 30000\n"
                "  compaction_threshold: 0.7\n"
                "tasks:\n  player:\n    provider: anthropic\n    model: claude-haiku-4-5\n")
            old = os.environ.get("BOUKENSHA_DIR")
            os.environ["BOUKENSHA_DIR"] = str(cfg_dir)
            try:
                cfg = Config()
                self.assertEqual(30000, cfg.agent_setting("max_turn_tokens"))
                self.assertEqual(0.7, cfg.agent_setting("compaction_threshold"))
                self.assertIsNone(cfg.agent_setting("max_iterations"))  # unset
            finally:
                if old is None:
                    os.environ.pop("BOUKENSHA_DIR", None)
                else:
                    os.environ["BOUKENSHA_DIR"] = old



class TestEveryCeilingCanBeSetAgentWide(unittest.TestCase):
    """The `agent:` block is a promise the settings table makes to a reader.

    Four of the five ceilings honoured it and the money ceiling did not: it read
    per-task settings alone, so a person wanting one budget across every task had
    nowhere to put it. Found by checking a doc's own count against the code rather than
    against the table beside it.
    """

    #: What `run_dsl` resolves through `Config.agent_setting`. The money ceiling is the
    #: one that was missing, and it is named here so removing it fails rather than
    #: quietly shrinking the promise.
    EXPECTED = {"max_iterations", "max_output_tokens", "max_turn_tokens",
                "max_turn_cost", "compaction_threshold"}

    def test_every_documented_limit_reads_the_agent_block(self):
        import re
        from pathlib import Path

        source = (Path(__file__).resolve().parents[1]
                  / "boukensha" / "run_dsl.py").read_text()
        found = set(re.findall(r'agent_setting\("([a-z_]+)"\)', source))
        self.assertEqual(self.EXPECTED, found,
                         f"missing from the agent block: {self.EXPECTED - found}")

    def test_the_money_ceiling_takes_an_agent_wide_default(self):
        # The behaviour, not only the call site: a per-task value still wins, and the
        # agent-wide one is what applies when the task says nothing.
        self.assertEqual(0.25, Player.max_turn_cost({}, default=0.25))
        self.assertEqual(0.5, Player.max_turn_cost({"max_turn_cost": 0.5}, default=0.25))

    def test_and_the_code_default_still_applies_when_neither_is_set(self):
        self.assertEqual(Player.DEFAULT_MAX_TURN_COST, Player.max_turn_cost({}))


if __name__ == "__main__":
    unittest.main()
