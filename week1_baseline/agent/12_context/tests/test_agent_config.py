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


if __name__ == "__main__":
    unittest.main()
