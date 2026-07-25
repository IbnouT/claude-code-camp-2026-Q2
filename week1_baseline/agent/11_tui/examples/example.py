"""The TUI step's example: launch the real thing.

A thin launcher, the right shape for an interactive full-screen app: with a
terminal attached it boots the journey TUI itself; without one
(CI, piped) it falls back to the plain line REPL (the same ``--no-tui`` path
the installed command offers), which exits cleanly at end of input. Nothing is
simulated: every guarantee is pinned by ``tests/`` (run by the step launcher).
"""

import os
import sys
from pathlib import Path

STEP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STEP_DIR))
os.environ.setdefault("BOUKENSHA_DIR", str(STEP_DIR.parents[2] / ".boukensha"))

from boukensha import repl  # noqa: E402
from boukensha.config import Config  # noqa: E402
from boukensha.version import __version__  # noqa: E402

def replay():
    """RECORDED REPLAY: a real captured session through the real TUI.

    No live model and no live MUD: ``examples/data/replay_session.jsonl`` is
    the event stream of an actual boukensha run against real tbaMUD (verbatim,
    only the bulky prompt message dumps slimmed to their counts), fed on a
    timer. The dashboard's room and vitals fill in, humanized actions land in
    RECENT, and the Feed tab builds the readable card history. A demo for
    humans, deterministic verification stays in tests/.
    """
    import asyncio as aio
    import json
    from boukensha.tui import LogEvent, Tui

    events = [json.loads(line) for line in
              (STEP_DIR / "examples" / "data"
               / "replay_session.jsonl").read_text().splitlines()]

    class _ReplayRepl:
        PROMPT = "replay> "
        version, model = __version__, "recorded replay"
        turn = tokens_in = tokens_out = 0
        cost = 0.0
        context_window = None
        commands = ()
        servers: dict = {}

        class _L:
            def subscribe(self, cb):
                pass
        logger = _L()

        class _R:
            tools: dict = {}

            def __len__(self):
                return 0
        registry = _R()

        def banner(self):
            return ("RECORDED REPLAY - no live model, no live MUD.\n"
                    "A real captured tbaMUD session streams through the TUI.\n"
                    "Ctrl+T cycles Dashboard / Feed. Ctrl+D quits.")

        def on_output(self, cb):
            pass

        def handle_command(self, line):
            return "quit" if line in ("/exit", "/quit") else "command"

        def run_turn(self, text):
            pass

        def cancel_turn(self):
            return False

    class ReplayTui(Tui):
        def on_mount(self) -> None:
            super().on_mount()
            self.notify("RECORDED REPLAY - no live model or MUD", timeout=6)
            self.run_worker(self._feed())

        async def _feed(self) -> None:
            for event in events:
                self.post_message(LogEvent(event))
                # Results linger a beat so the trace reads at watching speed.
                await aio.sleep(
                    0.35 if event.get("phase") == "tool_result" else 0.1)
            self.notify("replay complete - Ctrl+T for the map - Ctrl+D quits",
                        timeout=10)

    ReplayTui(_ReplayRepl(), splash=False).run()


if "--replay" in sys.argv:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("--replay needs a terminal to display the TUI.")
        sys.exit(0)
    replay()
    sys.exit(0)


cfg = Config()
interactive = (sys.stdin.isatty() and sys.stdout.isatty()
               and "--no-tui" not in sys.argv)
print(f"boukensha v{__version__} · step 11: the TUI")
print(f"config:  {cfg.dir}")
print(f"servers: {', '.join(cfg.mcp_servers()) or 'none configured'}")
if interactive:
    print("Launching the journey TUI (Ctrl+T: tabs · Ctrl+F: search ·")
    print("Ctrl+P: commands · Esc: cancel turn · Ctrl+D: quit) …")
    repl(tui=True)
else:
    print("No TTY (or --no-tui): falling back to the plain REPL.")
    print("Guarantees live in tests/: uv run python -m unittest discover -s tests -t .")
    repl(tui=False)
