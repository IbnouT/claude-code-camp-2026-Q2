"""The top-level agent: config block (decision A4a), resolved layered.

A per-task value wins, else the agent-wide default, else the code default. This
adopts the reference's step-12 agent: block while keeping the task-level
overrides our earlier steps have always had.
"""

import os
import tempfile
import unittest
from pathlib import Path

from boukensha.config import CAPABILITIES, Config
from boukensha.errors import ConfigError
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


class TestPlayerProfileConfig(unittest.TestCase):
    def test_selected_profile_resolves_character_and_profile_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = Path(tmp) / ".boukensha"
            profile_dir = cfg_dir / "profiles" / "scout"
            profile_dir.mkdir(parents=True)
            (cfg_dir / "settings.yaml").write_text(
                "gateway:\n"
                "  connection:\n"
                "    player_profile: scout\n"
                "  players:\n"
                "    scout:\n"
                "      character: ScoutName\n"
                "      password_env: SCOUT_PASSWORD\n"
            )
            (profile_dir / ".env").write_text(
                "SCOUT_PASSWORD=scout-secret\n"
            )
            old_dir = os.environ.get("BOUKENSHA_DIR")
            old_secret = os.environ.pop("SCOUT_PASSWORD", None)
            os.environ["BOUKENSHA_DIR"] = str(cfg_dir)
            try:
                cfg = Config()
                self.assertEqual("scout", cfg.mud_player_profile)
                self.assertEqual("ScoutName", cfg.mud_username)
                self.assertEqual("scout-secret", cfg.mud_password)
            finally:
                if old_dir is None:
                    os.environ.pop("BOUKENSHA_DIR", None)
                else:
                    os.environ["BOUKENSHA_DIR"] = old_dir
                if old_secret is None:
                    os.environ.pop("SCOUT_PASSWORD", None)
                else:
                    os.environ["SCOUT_PASSWORD"] = old_secret



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


class TestCapabilities(unittest.TestCase):
    def _config(self, text: str) -> Config:
        self._tmp = tempfile.TemporaryDirectory()
        cfg_dir = Path(self._tmp.name) / ".boukensha"
        cfg_dir.mkdir()
        (cfg_dir / "settings.yaml").write_text(text)
        self._old = os.environ.get("BOUKENSHA_DIR")
        os.environ["BOUKENSHA_DIR"] = str(cfg_dir)
        self.addCleanup(self._restore)
        return Config()

    def _restore(self) -> None:
        if self._old is None:
            os.environ.pop("BOUKENSHA_DIR", None)
        else:
            os.environ["BOUKENSHA_DIR"] = self._old
        self._tmp.cleanup()

    def test_capabilities_default_off(self):
        cfg = self._config("tasks:\n  player:\n    provider: anthropic\n")
        for name in CAPABILITIES:
            self.assertFalse(cfg.capability(name))
            self.assertEqual({}, cfg.capability_settings(name))

    def test_capability_reads_enabled_and_settings(self):
        cfg = self._config(
            "capabilities:\n"
            "  survival:\n"
            "    enabled: true\n"
            "    rest_threshold: 0.2\n")
        self.assertTrue(cfg.capability("survival"))
        self.assertFalse(cfg.capability("navigation"))
        self.assertEqual(
            0.2, cfg.capability_settings("survival")["rest_threshold"])

    def test_unknown_capability_raises(self):
        cfg = self._config("tasks: {}\n")
        with self.assertRaises(ConfigError):
            cfg.capability("telepathy")
