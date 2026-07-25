"""The Tui over the real chain: one scripted turn, end to end, offline.

The full assembly (Context, Registry, PromptBuilder, Client, Logger, Repl) runs
under the Tui with a scripted transport, so the pipeline the live command uses
is proven without a network or a key.
"""

import asyncio
import unittest

from boukensha.tui import Tui

from .helper import (
    StubTransport, add_ping_tool, build_repl, end_turn, ok, pane_text, tool_use,
)


async def _settle(pilot, rounds=8):
    for _ in range(rounds):
        await asyncio.sleep(0.03)
        await pilot.pause()


class TestChain(unittest.IsolatedAsyncioTestCase):
    async def test_a_scripted_turn_renders_reply_activity_and_status(self):
        repl, _ = build_repl(
            StubTransport(ok(tool_use("ping")), ok(end_turn("A dim corridor."))),
            "tui_chain", setup=add_ping_tool)
        app = Tui(repl, splash=False)
        async with app.run_test(size=(90, 24)) as pilot:
            await pilot.click("#input")
            for ch in "look":
                await pilot.press(ch)
            await pilot.press("enter")
            await _settle(pilot, rounds=12)

            # The journey is a set of readable cards, one per meaningful beat.
            by_kind = {}
            for card in app.present.cards:
                by_kind.setdefault(card.kind, []).append(card.body)
            self.assertIn("look", by_kind.get("you", []))          # the user line
            self.assertTrue(any("ping" in b for b in by_kind.get("action", [])))
            self.assertTrue(any("A dim corridor." in b
                                for b in by_kind.get("thinking", [])))
            # The raw trace is de-noised out: no iteration/token plumbing beats.
            self.assertEqual({"you", "action", "thinking"}, set(by_kind))
            # The REPL feed is silenced, so its "[iteration N]" / "-> tool"
            # activity lines never leak into thinking through on_output.
            self.assertTrue(repl.quiet)
            self.assertFalse(any("iteration" in b.lower()
                                 for b in by_kind.get("thinking", [])))

            # Durable numbers read straight from the Repl.
            self.assertEqual(1, repl.turn)
            self.assertIn("1 turns", app._progress_line)
            self.assertIn("$", app._header_line)
