"""Demo and smoke test for the configuration step.

Runs entirely offline: no network, no API keys. It walks the story of ``Config``
resolving a directory and loading settings, a task resolving its provider,
model, and system prompt, and the guarantees around all of it, tolerance to a
missing config, strictness on a malformed one, override vs default prompt, then
pins the same behaviour with compact assertions at the end.
"""

import os
import tempfile
from pathlib import Path

from boukensha import Config, ConfigError, Player

REPO_ROOT = Path(__file__).resolve().parents[4]


def section(title: str) -> None:
    print(f"\n-- {title} --")


print("=== boukensha · step 00: configuration ===")

# Resolve against the repo's .boukensha by walking up from this file's tree.
config = Config()
player = config.tasks("player")
system_prompt = Player.system_prompt(player, config.user_prompt_path(Player.task_name))

section("resolved configuration")
print(f"Config dir:      {config.dir}")
print(f"Tasks:           {', '.join(config.tasks())}")
print(f"Provider:        {Player.provider(player)}")
print(f"Model:           {Player.model(player)}")
print(f"Prompt override: {Player.prompt_override(player)}")
print(f"System prompt:   {(system_prompt or '')[:60]}...")
print(f"MUD target:      {config.mud_host}:{config.mud_port} as {config.mud_username}")
print(f"API key set?     {bool(os.environ.get('ANTHROPIC_API_KEY'))}")
print(f"MUD password?    {bool(config.mud_password)}")
print(config)

section("directory resolution")
with tempfile.TemporaryDirectory() as tmp:
    os.environ["BOUKENSHA_DIR"] = tmp
    try:
        print(f"BOUKENSHA_DIR set   -> {Config().dir}   (explicit override)")
    finally:
        del os.environ["BOUKENSHA_DIR"]
print(f"walking up from cwd -> {config.dir}   (nearest .boukensha)")
print("neither of the above -> ~/.boukensha   (default install location)")

section("empty config directory (fresh install runs on defaults)")
with tempfile.TemporaryDirectory() as tmp:
    os.environ["BOUKENSHA_DIR"] = tmp
    try:
        empty = Config()
        print(f"tasks:      {list(empty.tasks()) or '(none)'}")
        print(f"MUD target: {empty.mud_host}:{empty.mud_port}   (defaults, no settings.yaml)")
    finally:
        del os.environ["BOUKENSHA_DIR"]

section("malformed settings.yaml names the offending key")
with tempfile.TemporaryDirectory() as tmp:
    (Path(tmp) / "settings.yaml").write_text("tasks:\n  player: not-a-mapping\n")
    os.environ["BOUKENSHA_DIR"] = tmp
    try:
        Config()
    except ConfigError as err:
        print(f"ConfigError: {err}")
    finally:
        del os.environ["BOUKENSHA_DIR"]

section("system prompt resolution: override wins, else the packaged default")
with tempfile.TemporaryDirectory() as tmp:
    (Path(tmp) / "settings.yaml").write_text(
        "tasks:\n  player:\n    provider: anthropic\n    model: m\n"
        "    prompt_override:\n      system: true\n"
    )
    os.environ["BOUKENSHA_DIR"] = tmp
    try:
        cfg = Config()
        settings = cfg.tasks("player")
        override_path = cfg.user_prompt_path("player")
        default = Player.system_prompt(settings, override_path)
        print(f"override on, no file -> default:  {default[:40]!r}...")
        override_path.parent.mkdir(parents=True, exist_ok=True)
        override_path.write_text("CUSTOM: you are the override prompt.")
        custom = Player.system_prompt(settings, override_path)
        print(f"override file present -> override: {custom!r}")
    finally:
        del os.environ["BOUKENSHA_DIR"]

# -- assertions (offline) --------------------------------------------------


def rejected(build, error):
    try:
        build()
        return False
    except error:
        return True


with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp).resolve()
    os.environ["BOUKENSHA_DIR"] = tmp
    try:
        override_dir = Config().dir
        empty_tasks = Config().tasks()
    finally:
        del os.environ["BOUKENSHA_DIR"]

with tempfile.TemporaryDirectory() as tmp:
    (Path(tmp) / "settings.yaml").write_text("- not\n- a mapping\n")
    os.environ["BOUKENSHA_DIR"] = tmp
    try:
        malformed_rejected = rejected(Config, ConfigError)
    finally:
        del os.environ["BOUKENSHA_DIR"]

checks = {
    "1 the resolved system prompt is non-empty":
        bool(system_prompt and system_prompt.strip()),
    "2 walking up from the step directory finds the repo .boukensha":
        config.dir == REPO_ROOT / ".boukensha",
    "3 BOUKENSHA_DIR overrides discovery when set":
        override_dir == tmp_path,
    "4 a missing settings.yaml runs on defaults, not raising":
        empty_tasks == {},
    "5 a malformed settings.yaml raises ConfigError":
        malformed_rejected,
}

section("assertions")
for label, passed in checks.items():
    print(f"  {'✓' if passed else '✗'} {label}")
assert all(checks.values()), "one or more config guarantees failed"
print()
print("assertions passed (5) ✓")
