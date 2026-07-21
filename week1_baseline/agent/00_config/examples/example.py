"""Smoke test for the configuration step.

Prints the resolved configuration and asserts the two invariants that matter:
walking up from the current directory finds the repo's ``.boukensha``, and
``BOUKENSHA_DIR`` overrides everything when set.
"""

import os
import tempfile
from pathlib import Path

from boukensha import Config, Player

REPO_ROOT = Path(__file__).resolve().parents[4]

config = Config()
player = config.tasks("player")
system_prompt = Player.system_prompt(player, config.user_prompt_path(Player.task_name))

print("=== boukensha · step 00: configuration ===")
print()
print(f"Config dir:      {config.dir}")
print(f"Tasks:           {', '.join(config.tasks())}")
print()
print("-- player task --")
print(f"Provider:        {Player.provider(player)}")
print(f"Model:           {Player.model(player)}")
print(f"Prompt override: {Player.prompt_override(player)}")
print(f"System prompt:   {(system_prompt or '')[:60]}...")
print()
print(f"MUD target:      {config.mud_host}:{config.mud_port} as {config.mud_username}")
print(f"API key set?     {bool(os.environ.get('ANTHROPIC_API_KEY'))}")
print(f"MUD password?    {bool(config.mud_password)}")
print()
print(config)

# -- invariants ------------------------------------------------------------
assert system_prompt and system_prompt.strip(), "system prompt must resolve non-empty"
assert config.dir == REPO_ROOT / ".boukensha", \
    "walking up from the step directory must find the repo config"

with tempfile.TemporaryDirectory() as tmp:
    os.environ["BOUKENSHA_DIR"] = tmp
    try:
        assert Config().dir == Path(tmp).resolve(), \
            "BOUKENSHA_DIR must override discovery when set"
    finally:
        del os.environ["BOUKENSHA_DIR"]

print()
print("assertions passed ✓")
