"""The Tui over a FakeRepl: routing, cancellation, the two tabs, safety.

Pure front-end tests: the FakeRepl records what the Tui drives, so each test
asserts on routing and rendering with no agent and no network behind it.
Textual's headless ``run_test`` harness supplies the Pilot. Every interactive
surface (splash, tab switch, feed search, palette) is driven for real so a
render-time crash fails here, not in the terminal.
"""

import asyncio
import unittest

from boukensha.tui import LogEvent, ReplCommandProvider, Tui

from .helper import (
    BlockingCommandFakeRepl, BlockingFakeRepl, FakeRepl, pane_text)


async def _type(pilot, text):
    for ch in text:
        await pilot.press(ch)


async def _settle(pilot, rounds=6):
    for _ in range(rounds):
        await asyncio.sleep(0.03)
        await pilot.pause()


LOOK = ("\x1b[0;33mThe Temple\x1b[0m\r\n   A grand hall.\r\n"
        "\x1b[0;36m[ Exits: n s ]\x1b[0m\r\n24H 100M 85V (news) (motd) > ")


class TestRouting(unittest.IsolatedAsyncioTestCase):
    async def test_plain_text_launches_a_turn(self):
        repl = FakeRepl()
        async with Tui(repl, splash=False).run_test() as pilot:
            await pilot.click("#input")
            await _type(pilot, "look around")
            await pilot.press("enter")
            await _settle(pilot)
        self.assertEqual(["look around"], repl.turn_calls)
        self.assertEqual([], repl.command_calls)

    async def test_a_slash_command_never_reaches_run_turn(self):
        repl = FakeRepl()
        async with Tui(repl, splash=False).run_test() as pilot:
            await pilot.click("#input")
            await _type(pilot, "/help")
            await pilot.press("enter")
            await _settle(pilot)
        self.assertEqual(["/help"], repl.command_calls)
        self.assertEqual([], repl.turn_calls)

    async def test_double_slash_escape_reaches_the_agent(self):
        repl = FakeRepl()
        async with Tui(repl, splash=False).run_test() as pilot:
            await pilot.click("#input")
            await _type(pilot, "//say hello")
            await pilot.press("enter")
            await _settle(pilot)
        self.assertEqual(["/say hello"], repl.turn_calls)
        self.assertEqual([], repl.command_calls)

    async def test_quit_exits_the_app(self):
        repl = FakeRepl()
        app = Tui(repl, splash=False)
        async with app.run_test() as pilot:
            await pilot.click("#input")
            await _type(pilot, "/quit")
            await pilot.press("enter")
            await _settle(pilot)
        self.assertFalse(app.is_running)

    async def test_a_blocking_command_does_not_freeze_the_app(self):
        repl = BlockingCommandFakeRepl()
        app = Tui(repl, splash=False)
        async with app.run_test() as pilot:
            await pilot.click("#input")
            await _type(pilot, "/retry")
            await pilot.press("enter")
            await _settle(pilot, rounds=3)
            self.assertTrue(repl.started.is_set())
            await pilot.click("#input")
            await _type(pilot, "abc")
            self.assertEqual("abc", app.query_one("#input").value)
            repl.release.set()
            await _settle(pilot)
        self.assertEqual(["/retry"], repl.command_calls)


class TestCancellation(unittest.IsolatedAsyncioTestCase):
    async def test_escape_cancels_through_the_repl(self):
        repl = BlockingFakeRepl()
        async with Tui(repl, splash=False).run_test() as pilot:
            await pilot.click("#input")
            await _type(pilot, "go north")
            await pilot.press("enter")
            await asyncio.get_event_loop().run_in_executor(
                None, repl.started.wait, 2)
            await pilot.press("escape")
            await _settle(pilot)
        self.assertEqual(1, repl.cancel_calls)

    async def test_escape_is_a_no_op_when_idle(self):
        repl = FakeRepl()
        async with Tui(repl, splash=False).run_test() as pilot:
            await pilot.press("escape")
            await _settle(pilot, rounds=2)
        self.assertEqual(1, repl.cancel_calls)
        self.assertEqual([], repl.turn_calls)


class TestDashboard(unittest.IsolatedAsyncioTestCase):
    async def test_the_frame_widgets_exist(self):
        repl = FakeRepl()
        app = Tui(repl, splash=False)
        async with app.run_test() as pilot:
            await _settle(pilot, rounds=2)
            for widget in ("#header", "#tabs", "#mud", "#recent", "#feed",
                           "#feed-search", "#progress", "#input"):
                self.assertIsNotNone(app.query_one(widget))

    async def test_honest_empty_states(self):
        repl = FakeRepl()
        app = Tui(repl, splash=False)
        async with app.run_test() as pilot:
            await _settle(pilot, rounds=2)
            self.assertIn("Waiting for the first room", app._render_mud().plain)
            self.assertIn("no actions yet", app._render_recent().plain)
            self.assertIn("awaiting your first instruction",
                          app._render_goal().plain)

    async def test_goal_pins_the_latest_instruction(self):
        repl = FakeRepl()
        app = Tui(repl, splash=False)
        async with app.run_test() as pilot:
            await pilot.click("#input")
            await _type(pilot, "find and defeat the minotaur")
            await pilot.press("enter")
            await _settle(pilot)
            self.assertIn("find and defeat the minotaur",
                          app._render_goal().plain)

    async def test_counters_come_from_the_repl_not_a_shadow(self):
        repl = FakeRepl()
        repl.turn = 7
        repl.cost = 0.0123
        app = Tui(repl, splash=False)
        async with app.run_test() as pilot:
            await _settle(pilot, rounds=2)
            self.assertIn("7 turns", app._progress_line)
            self.assertIn("$0.0123", app._header_line)

    async def test_vitals_room_and_action_populate_the_dashboard(self):
        repl = FakeRepl()
        app = Tui(repl, splash=False)
        async with app.run_test() as pilot:
            app.post_message(LogEvent({"phase": "tool_call", "name": "tbamud__move",
                                       "args": {"direction": "west"}, "id": "a"}))
            app.post_message(LogEvent({"phase": "tool_result", "name": "tbamud__move",
                                       "result": LOOK, "tool_use_id": "a"}))
            await _settle(pilot, rounds=4)
            # Vitals reach the header, humanized action reaches RECENT, the room
            # reaches the main MUD area.
            self.assertIn("HP 24", app._header_line)
            self.assertIn("move west", app._render_recent().plain)
            self.assertIn("The Temple", app._render_mud().plain)
            self.assertIn("exits: north, south", app._render_mud().plain)


class TestFeed(unittest.IsolatedAsyncioTestCase):
    async def test_feed_shows_cards_and_search_filters(self):
        repl = FakeRepl()
        app = Tui(repl, splash=False)
        async with app.run_test(size=(100, 30)) as pilot:
            app.post_message(LogEvent({"phase": "tool_call", "name": "tbamud__look",
                                       "args": {}, "id": "a"}))
            app.post_message(LogEvent({"phase": "tool_result", "name": "tbamud__look",
                                       "result": LOOK, "tool_use_id": "a"}))
            app.post_message(LogEvent({"phase": "reasoning",
                                       "text": "Heading to the market."}))
            await _settle(pilot, rounds=3)
            await pilot.press("ctrl+t")            # switch to the Feed tab
            await _settle(pilot, rounds=3)
            feed = pane_text(app, "feed")
            self.assertIn("The Temple", feed)      # room card
            self.assertIn("-> look", feed)         # humanized action card
            self.assertIn("Heading to the market", feed)  # thinking card

            await pilot.click("#feed-search")
            await _type(pilot, "temple")
            await _settle(pilot, rounds=3)
            filtered = pane_text(app, "feed")
            self.assertIn("The Temple", filtered)
            self.assertNotIn("Heading to the market", filtered)


class TestTabsAndSplash(unittest.IsolatedAsyncioTestCase):
    async def test_ctrl_t_cycles_dashboard_and_feed(self):
        from textual.widgets import TabbedContent
        repl = FakeRepl()
        app = Tui(repl, splash=False)
        async with app.run_test() as pilot:
            await _settle(pilot, rounds=2)
            tabs = app.query_one("#tabs", TabbedContent)
            self.assertEqual("tab-dashboard", tabs.active)
            await pilot.press("ctrl+t")
            await _settle(pilot, rounds=2)
            self.assertEqual("tab-feed", tabs.active)
            await pilot.press("ctrl+t")
            await _settle(pilot, rounds=2)
            self.assertEqual("tab-dashboard", tabs.active)

    async def test_ctrl_f_focuses_feed_search(self):
        from textual.widgets import TabbedContent
        repl = FakeRepl()
        app = Tui(repl, splash=False)
        async with app.run_test() as pilot:
            await _settle(pilot, rounds=2)
            await pilot.press("ctrl+f")
            await _settle(pilot, rounds=2)
            self.assertEqual("tab-feed",
                             app.query_one("#tabs", TabbedContent).active)
            self.assertEqual("feed-search", app.focused.id)

    async def test_splash_opens_by_default_and_enter_starts(self):
        from boukensha.tui import SplashScreen
        repl = FakeRepl()
        app = Tui(repl)
        async with app.run_test() as pilot:
            await _settle(pilot, rounds=3)
            self.assertIsInstance(app.screen, SplashScreen)
            await pilot.press("enter")
            await _settle(pilot, rounds=3)
            self.assertNotIsInstance(app.screen, SplashScreen)

    async def test_info_reopens_the_session_card(self):
        from boukensha.tui import SplashScreen
        repl = FakeRepl()
        app = Tui(repl, splash=False)
        async with app.run_test() as pilot:
            await _settle(pilot, rounds=2)
            app.submit_line("/info")
            await _settle(pilot, rounds=3)
            self.assertIsInstance(app.screen, SplashScreen)
            self.assertEqual([], repl.command_calls)  # /info is the TUI's own
            await pilot.press("escape")
            await _settle(pilot, rounds=2)
            self.assertNotIsInstance(app.screen, SplashScreen)


class TestSafety(unittest.IsolatedAsyncioTestCase):
    async def test_bracket_and_ansi_mud_text_never_crashes_rendering(self):
        # MUD text is full of brackets and color escapes. Cards render it as
        # styled Text (never parsed markup), and ANSI is stripped, so a room
        # with "[ Exits: n s ]" and \x1b codes renders cleanly.
        repl = FakeRepl()
        app = Tui(repl, splash=False)
        async with app.run_test(size=(100, 30)) as pilot:
            app.post_message(LogEvent({"phase": "tool_call", "name": "tbamud__look",
                                       "args": {}, "id": "a"}))
            app.post_message(LogEvent({"phase": "tool_result", "name": "tbamud__look",
                                       "result": LOOK, "tool_use_id": "a"}))
            await _settle(pilot, rounds=3)
            mud = app._render_mud().plain
            self.assertIn("A grand hall", mud)
            self.assertNotIn("\x1b", mud)
            self.assertNotIn("100M", mud)          # game-prompt telemetry dropped

    async def test_a_failed_turn_surfaces_an_error_card(self):
        class Boom(FakeRepl):
            def run_turn(self, text):
                raise RuntimeError("kaboom")
        repl = Boom()
        app = Tui(repl, splash=False)
        async with app.run_test() as pilot:
            await pilot.click("#input")
            await _type(pilot, "go")
            await pilot.press("enter")
            await _settle(pilot, rounds=4)
            kinds = [(c.kind, c.body) for c in app.present.cards]
            self.assertTrue(any(k == "error" and "kaboom" in b for k, b in kinds))


class TestCombatUI(unittest.IsolatedAsyncioTestCase):
    async def test_fight_shows_the_combat_box_and_fighting_avatar(self):
        repl = FakeRepl()
        app = Tui(repl, splash=False)
        async with app.run_test(size=(110, 34)) as pilot:
            app.post_message(LogEvent({
                "phase": "tool_call", "name": "tbamud__attack",
                "args": {"target": "fido"}, "id": "a"}))
            app.post_message(LogEvent({
                "phase": "tool_result", "name": "tbamud__attack",
                "result": "The beastly fido is here, fighting YOU!\r\n"
                          "You swing at the fido, but miss!\r\n91H 100M 51V > ",
                "tool_use_id": "a"}))
            await _settle(pilot, rounds=4)
            self.assertTrue(app.present.combat_active)
            self.assertTrue(app.query_one("#combat").has_class("on"))
            self.assertTrue(app.query_one("#tabs").has_class("combat"))
            self.assertIn("fighting", app._render_avatar().plain)
            self.assertIn("IN COMBAT", app._render_combat().plain)

    async def test_box_hides_when_not_fighting(self):
        repl = FakeRepl()
        app = Tui(repl, splash=False)
        async with app.run_test(size=(110, 34)) as pilot:
            await _settle(pilot, rounds=2)
            self.assertFalse(app.query_one("#combat").has_class("on"))
            self.assertFalse(app.query_one("#tabs").has_class("combat"))


class TestPalette(unittest.IsolatedAsyncioTestCase):
    async def test_palette_offers_repl_commands_and_info(self):
        class Cmd:
            def __init__(self, name, summary):
                self.name, self.summary = name, summary
        repl = FakeRepl()
        repl.commands = (Cmd("/cost", "usd"),)
        app = Tui(repl, splash=False)
        async with app.run_test() as pilot:
            await _settle(pilot, rounds=2)
            provider = ReplCommandProvider(app.screen)
            names = [hit.text.plain if hasattr(hit.text, "plain") else str(hit.text)
                     async for hit in provider.search("in")]
            self.assertTrue(any("/info" in n for n in names))
