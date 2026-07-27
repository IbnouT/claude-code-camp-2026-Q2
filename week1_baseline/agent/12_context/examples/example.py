"""Step 12: context management. Launch the app and watch it manage its window.

A thin launcher, the right shape for an interactive application: with a terminal
attached it boots the journey TUI against the configured MUD and hands over
control, and without one (CI, piped) it falls back to the plain line REPL, the
same ``--no-tui`` path the installed command offers.

What makes this step visible while you play is the context window. Pass
``--window N`` to set it: a small window means an ordinary session crosses the
compaction threshold within a couple of turns, so you watch the agent free its own
context. The footer names the reason a turn ended and a compaction card appears in
the Feed, which is what those were built for. Compaction is evaluated at the start
of a turn, so it shows on the turn after the one that filled the window, and
``/compact`` forces one whenever you want.

Nothing here is scripted and nothing is asserted. Every systematic guarantee lives
in ``tests/``, which is their single home, including the deterministic proof that a
multi-turn session compacts.
"""

import os
import sys
from pathlib import Path

STEP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STEP_DIR))
os.environ.setdefault("BOUKENSHA_DIR", str(STEP_DIR.parents[2] / ".boukensha"))

from boukensha import repl  # noqa: E402
from boukensha.compaction import prefix_tokens  # noqa: E402
from boukensha.config import Config  # noqa: E402
from boukensha.tasks import Player  # noqa: E402
from boukensha.version import __version__  # noqa: E402


def chosen_window(argv):
    """``--window N`` overrides the model's own window, else the model decides.

    Passing a small number is how a person forces compaction to happen during a
    short session instead of after an hour of play. Left alone, the window comes
    from the backend catalog like any normal run.
    """
    if "--window" in argv:
        try:
            return int(argv[argv.index("--window") + 1])
        except (IndexError, ValueError):
            print("--window needs a number, ignoring it.")
    return None


cfg = Config()
window = chosen_window(sys.argv)
interactive = (sys.stdin.isatty() and sys.stdout.isatty()
               and "--no-tui" not in sys.argv)

settings = cfg.tasks(Player.task_name)
system = Player.system_prompt(
    settings, override_path=cfg.user_prompt_path(Player.task_name))
prefix = prefix_tokens(system, None)

print(f"boukensha v{__version__} · step 12: context management")
print(f"config:  {cfg.dir}")
print(f"servers: {', '.join(cfg.mcp_servers()) or 'none configured'}")
if window is None:
    print("window:  the model's own, from the catalog. Pass --window N (for "
          "example 8000)")
    print("         to force compaction during a short session.")
else:
    print(f"window:  {window} tokens, so compaction fires at {int(window * 0.85)}")
    if window <= prefix:
        print(f"         careful: the system prompt alone is about {prefix} tokens, "
              "so this")
        print("         window leaves compaction nothing it can win. Raise it.")
print()

if interactive:
    print("Launching the journey TUI. Play a few turns and watch the header's ctx")
    print("figure climb: a compaction card appears in the Feed once it crosses.")
    print("(Ctrl+T: tabs · Ctrl+F: search · Ctrl+P: commands · /compact forces one")
    print("· /info session card · Esc cancels a turn · Ctrl+D quits)")
    repl(tui=True, context_window=window)
else:
    print("No TTY (or --no-tui): falling back to the plain REPL.")
    print("Guarantees live in tests/: uv run python -m unittest discover -s tests -t .")
    repl(tui=False, context_window=window)
