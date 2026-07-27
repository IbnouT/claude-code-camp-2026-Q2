"""The header's ceiling chips: a live counter, and a measurement that never hides.

Two defects found by playing rather than by any test, which is the argument for the
launcher being a launcher.

The iteration chip read `self._live["iteration"]` and nothing ever wrote it, so it
displayed `iter 0/125` through a turn that ran 125 iterations and stopped on that very
ceiling. A default standing in for a value nobody assigns fails silently forever,
because the type is right and the number is plausible.

Disabling a ceiling also removed its number. `max_turn_tokens: 0` turns off the limit,
and the token count vanished with it, which contradicts the argument that volume
processed is a metric in its own right.
"""

import asyncio
import unittest

from boukensha.context import Context
from boukensha.tui import Tui

from .tui_helper import FakeRepl


def _ctx(tokens=0, cost=0.0):
    """A real Context, since the header reads a real one.

    Stubbing its surface here would only test the stub. It holds no I/O, so a
    real one is as hermetic as a fake and cannot drift from what ships.
    """
    ctx = Context()
    ctx.turn_tokens = tokens
    ctx.current_tokens = tokens
    ctx.add_turn_cost(cost)
    return ctx


def _repl(max_iterations=25, max_turn_tokens=60_000, max_turn_cost=None,
          tokens=0, cost=0.0, session_cost=0.0):
    repl = FakeRepl()
    repl.max_iterations = max_iterations
    repl.max_turn_tokens = max_turn_tokens
    repl.max_turn_cost = max_turn_cost
    repl.context = _ctx(tokens=tokens, cost=cost)
    repl.cost = session_cost
    return repl


class TestTheIterationChipCounts(unittest.IsolatedAsyncioTestCase):
    async def test_a_turn_running_two_iterations_reports_two(self):
        app = Tui(_repl(), splash=False)
        async with app.run_test() as pilot:
            emit = app._repl.logger._cb
            emit({"phase": "iteration", "n": 1, "max": 25})
            emit({"phase": "iteration", "n": 2, "max": 25})
            for _ in range(6):
                await asyncio.sleep(0.03)
                await pilot.pause()
            self.assertEqual(2, app._live["iteration"])
            # The chip lives in the footer now, beside the stop reason it
            # explains, and not in the game-state strip.
            self.assertIn("iter 2/25", app._progress_line)
            self.assertNotIn("iter", app._header_line)

    def test_the_counter_is_part_of_the_per_turn_reset(self):
        # The key has to exist in the idle state or it resets to nothing and the
        # chip goes back to reading a default. This is the whole defect in one
        # assertion: a key that is read must be a key that is written.
        self.assertIn("iteration", Tui._idle_live())
        self.assertEqual(0, Tui._idle_live()["iteration"])


class TestDisablingACeilingKeepsTheMeasurement(unittest.TestCase):
    """Turning off a limit turns off the limit, never the number."""

    def test_every_ceiling_set_reads_as_current_over_limit(self):
        app = Tui(_repl(max_turn_cost=0.25, tokens=1500, cost=0.1),
                  splash=False)
        labels = " ".join(app._ceiling_labels())
        self.assertIn("iter 0/25", labels)
        self.assertIn("1.5k/60.0k", labels)
        self.assertIn("$0.100/$0.25", labels)

    def test_a_disabled_token_ceiling_still_shows_the_tokens(self):
        app = Tui(_repl(max_turn_tokens=0, tokens=69_900), splash=False)
        labels = app._ceiling_labels()
        joined = " ".join(labels)
        self.assertTrue(any(l.startswith("tok ") for l in labels),
                        f"the token measurement vanished with its ceiling: {labels}")
        self.assertIn("69.9k", joined)
        # And with no ceiling there is no denominator to imply one.
        self.assertNotIn("69.9k/", joined)

    def test_a_disabled_iteration_ceiling_still_shows_the_iterations(self):
        app = Tui(_repl(max_iterations=0), splash=False)
        app._live["iteration"] = 7
        labels = app._ceiling_labels()
        self.assertIn("iter 7", labels)

    def test_no_ceiling_at_all_still_reports_all_three_measurements(self):
        app = Tui(_repl(max_iterations=0, max_turn_tokens=0, max_turn_cost=0,
                        tokens=8_400, session_cost=0.0564), splash=False)
        labels = app._ceiling_labels()
        joined = " ".join(labels)
        self.assertEqual(3, len(labels), f"a measurement went missing: {labels}")
        self.assertIn("iter 0", joined)
        self.assertIn("8.4k", joined)
        self.assertIn("$0.0564", joined)
        # Nothing can be close to tripping when nothing is set, so no chip is
        # marked as the one about to bite.
        self.assertEqual([], [l for l in labels if l.startswith("[")])


class TestTheHeaderIsGameStateOnly(unittest.TestCase):
    """Three domains shared one line, and only one of them is watched.

    Game state is watched continuously, agent economics are glanced at, and
    infrastructure is noise until it breaks. Interleaving them put the number
    that mattered wherever there happened to be room.
    """

    def _app(self, **kw):
        app = Tui(_repl(**kw), splash=False)
        state = app._journey.state
        state.vitals.update(hp=24, max_hp=24, mana=100, moves=2)
        state.char.update(level=1, gold=0)
        return app

    def test_the_header_carries_the_game_and_none_of_the_economics(self):
        app = self._app(tokens=8400, session_cost=0.0564)
        header = app._render_header()
        for expected in ("HP 24/24", "Mana 100", "Moves 2", "Lv 1", "Gold 0"):
            self.assertIn(expected, header)
        for banished in ("iter", "ctx", "tok", "$", "repeat"):
            self.assertNotIn(banished, header)

    def test_the_clock_is_gone(self):
        # The terminal has one, and it was competing with HP for width.
        header = self._app()._render_header()
        self.assertNotRegex(header, r"\d\d:\d\d:\d\d")

    def test_working_tools_are_a_dot_and_broken_tools_are_words(self):
        app = self._app()
        self.assertIn("\u25cf", app._render_header())
        self.assertNotIn("mud(", app._render_header())
        app._repl.registry = {}
        self.assertIn("NO TOOLS", app._render_header())

    def test_a_condition_reads_as_an_alert_not_as_a_stat(self):
        app = self._app()
        app._journey.state.status.update(hungry=True, thirsty=True)
        header = app._render_header()
        self.assertIn(f"{Tui.ALERT} hungry thirsty", header)
        # Not a bare word sitting in a row of dots like Mana 100 does.
        self.assertNotIn("\u00b7 hungry", header)

    def test_the_footer_carries_the_economics_beside_the_state(self):
        app = self._app(max_turn_cost=0.25, tokens=8400, cost=0.1)
        app._live["iteration"] = 4
        footer = app._progress_text()
        self.assertIn("ready", footer)
        self.assertIn("iter 4/25", footer)
        self.assertIn("8.4k", footer)
        self.assertIn("$0.100/$0.25", footer)


class TestOverflowIsExplicit(unittest.TestCase):
    """Silent clipping is the defect. Dropping and saying so is the fix."""

    ITEMS = [(0, "HP 24/24"), (1, "\u26a0 hungry"), (2, "Moves 2"),
             (3, "Mana 100"), (4, "Lv 1"), (5, "Gold 0")]

    def test_everything_fits_when_there_is_room(self):
        line = Tui._fit(self.ITEMS, 200)
        self.assertIn("Gold 0", line)
        self.assertNotIn("+", line)

    def test_the_lowest_priority_goes_first_and_the_loss_is_stated(self):
        line = Tui._fit(self.ITEMS, 40)
        self.assertLessEqual(len(line), 40)
        self.assertIn("HP 24/24", line)
        self.assertIn("\u26a0 hungry", line)
        self.assertNotIn("Gold 0", line)
        self.assertRegex(line, r"\+\d+\u2026")

    def test_it_fits_at_every_width_that_can_hold_the_marker(self):
        """The real guarantee, stated at its actual limit.

        Below the marker's own length there is nothing honest to render, so the
        promise is made for every width that can hold it. That floor is asserted
        rather than assumed, so shortening or lengthening the marker cannot
        quietly widen the range where the line overruns.
        """
        floor = len(Tui.OVERFLOW_MARK.format(n=9))
        for width in range(floor, 90):
            line = Tui._fit(self.ITEMS, width)
            self.assertLessEqual(len(line), width,
                                 f"overran the line at width {width}: {line!r}")

    def test_an_unknown_width_drops_nothing(self):
        # Guessing a terminal is narrow and hiding real information is worse
        # than a line that wraps.
        line = Tui._fit(self.ITEMS, 0)
        self.assertIn("Gold 0", line)
        self.assertNotIn("+", line)


if __name__ == "__main__":
    unittest.main()
