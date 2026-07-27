"""Slash commands in the TUI: visible as results, and /clear clears the screen.

Two defects these guard. A command's output routed into the thinking view is
invisible where a person looks for it, and a `/clear` that drops the model's
history while leaving the cards on screen leaves the display and the model
disagreeing about what was said, which is worse than appearing to do nothing.
"""

import asyncio
import unittest

from boukensha.tui import Tui

from .tui_helper import FakeRepl


async def _settle(pilot, rounds=6):
    for _ in range(rounds):
        await asyncio.sleep(0.03)
        await pilot.pause()


async def _type(pilot, text):
    for ch in text:
        await pilot.press(ch)


class TestCommandOutputIsItsOwnCard(unittest.IsolatedAsyncioTestCase):
    async def test_command_output_is_a_command_card_not_the_agent_speaking(self):
        repl = FakeRepl(command_output="running tokens: 10 in / 2 out")
        app = Tui(repl, splash=False)
        async with app.run_test() as pilot:
            await pilot.click("#input")
            await _type(pilot, "/tokens")
            await pilot.press("enter")
            await _settle(pilot)
            kinds = [(c.kind, c.title, c.body) for c in app.present.cards]
            self.assertTrue(
                any(k == "command" and t == "/tokens" and "running tokens" in b
                    for k, t, b in kinds),
                f"no command card for /tokens: {kinds}")
            # It must NOT have become the agent's thinking.
            self.assertIsNone(app.present.current_thinking)

    async def test_an_agent_reply_is_still_a_thinking_card(self):
        repl = FakeRepl(turn_output="I have found the temple.")
        app = Tui(repl, splash=False)
        async with app.run_test() as pilot:
            await pilot.click("#input")
            await _type(pilot, "look")
            await pilot.press("enter")
            await _settle(pilot)
            self.assertIsNotNone(app.present.current_thinking)
            self.assertEqual(
                [], [c for c in app.present.cards if c.kind == "command"])


class TestUnknownCommandIsNotTheAgentThinking(unittest.IsolatedAsyncioTestCase):
    """The exact case a person hits: a command that does not exist.

    "unknown command: /continue (try /help)" carries no error marker, so it used to
    reach the thinking view and read as the agent's own reasoning. An error message
    masquerading as the model's thinking is worse than a missing feature, because it
    teaches the user to distrust the panel that shows what the agent is thinking.
    """

    async def test_the_rejection_renders_as_a_command_result(self):
        class Unknown(FakeRepl):
            def handle_command(self, line):
                self.command_calls.append(line)
                name = line.split()[0]
                if self._sink:
                    self._sink(f"unknown command: {name} (try /help)")
                return None

        repl = Unknown()
        app = Tui(repl, splash=False)
        async with app.run_test() as pilot:
            await pilot.click("#input")
            await _type(pilot, "/continue")
            await pilot.press("enter")
            await _settle(pilot)
            kinds = [(c.kind, c.title, c.body) for c in app.present.cards]
            self.assertTrue(
                any(k == "command" and "unknown command" in b for k, t, b in kinds),
                f"the rejection did not render as a command result: {kinds}")
            self.assertIsNone(app.present.current_thinking,
                              "a command rejection must never become thinking")


class TestClearClearsTheScreen(unittest.IsolatedAsyncioTestCase):
    async def test_clear_empties_the_feed_and_the_panels(self):
        repl = FakeRepl(command_output="history cleared")
        app = Tui(repl, splash=False)
        async with app.run_test() as pilot:
            await pilot.click("#input")
            await _type(pilot, "look around")
            await pilot.press("enter")
            await _settle(pilot)
            self.assertTrue(app.present.cards, "nothing on screen to clear")

            await pilot.click("#input")
            await _type(pilot, "/clear")
            await pilot.press("enter")
            await _settle(pilot)
            # The model forgot, so the screen must have forgotten too.
            self.assertEqual([], app.present.cards)
            self.assertIsNone(app.present.current_room)
            self.assertIsNone(app.present.current_thinking)


class TestCommandResultReachesTheCurrentTab(unittest.IsolatedAsyncioTestCase):
    """A Feed card is the record, and a toast is how the person who typed the
    command sees it while standing on the Dashboard."""

    def _record_toasts(self, app):
        seen = []
        app.notify = lambda body, **kw: seen.append((body, kw))
        return seen

    async def test_short_output_toasts_verbatim(self):
        repl = FakeRepl(command_output="running cost: $0.0123")
        app = Tui(repl, splash=False)
        async with app.run_test() as pilot:
            toasts = self._record_toasts(app)
            await pilot.click("#input")
            await _type(pilot, "/cost")
            await pilot.press("enter")
            await _settle(pilot)
        self.assertTrue(toasts, "no toast, so the Dashboard shows nothing")
        body, kw = toasts[-1]
        self.assertIn("running cost", body)
        self.assertEqual("/cost", kw.get("title"))

    async def test_long_output_is_summarized_and_points_at_the_feed(self):
        # /tools and /history do not fit a toast, so they must not be truncated
        # mid-content: name the first line and where the rest went.
        listing = "26 tool(s):\n" + "\n".join(f"  tool{i} - does a thing"
                                               for i in range(26))
        repl = FakeRepl(command_output=listing)
        app = Tui(repl, splash=False)
        async with app.run_test() as pilot:
            toasts = self._record_toasts(app)
            await pilot.click("#input")
            await _type(pilot, "/tools")
            await pilot.press("enter")
            await _settle(pilot)
        body, _kw = toasts[-1]
        self.assertIn("26 tool(s)", body)
        self.assertIn("Feed", body)
        self.assertNotIn("tool7", body, "the toast should summarize, not truncate")

    async def test_a_rejection_toasts_as_an_error(self):
        class Unknown(FakeRepl):
            def handle_command(self, line):
                self.command_calls.append(line)
                if self._sink:
                    self._sink(f"unknown command: {line.split()[0]} (try /help)")
                return None

        app = Tui(Unknown(), splash=False)
        async with app.run_test() as pilot:
            toasts = self._record_toasts(app)
            await pilot.click("#input")
            await _type(pilot, "/continue")
            await pilot.press("enter")
            await _settle(pilot)
        body, kw = toasts[-1]
        self.assertIn("unknown command", body)
        self.assertEqual("error", kw.get("severity"))


if __name__ == "__main__":
    unittest.main()
