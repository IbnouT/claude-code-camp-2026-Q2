"""JourneyParser against golden CircleMUD text, the shapes week0 verified.

Fixture text follows the exact line formats week0's ``mud_session.py`` parses
from real tbaMUD transcripts (room header + ``[ Exits: ]``, the ``H M V >``
prompt line, score/kill/death lines). No live MUD, no network.
"""

import unittest

from boukensha.journey import JourneyParser

LOOK_TEMPLE = (
    "The Temple Of Midgaard\n"
    "   You are in the southern end of the temple hall.\n"
    "[ Exits: n s ]\n"
    "90H 100M 92V >"
)
MOVE_SQUARE = (
    "The Temple Square\n"
    "   A large square. The temple is north.\n"
    "[ Exits: n e s w ]\n"
    "88H 100M 90V >"
)
SCORE = (
    "You are 25 years old.\n"
    "You have 66(100) hit, 30(100) mana and 90(100) movement points.\n"
    "You have 1200 exp, 340 gold coins.\n"
    "You need 800 exp to reach your next level.\n"
    "This ranks you as Gandalf the Acolyte (level 4)\n"
    "66H 30M 90V >"
)
KILL = "The beastly fido is dead! R.I.P.\nYou receive 25 experience points.\n90H 100M 92V >"
DEATH = "You are dead! Sorry...\n"
NOWAY = "Alas, you cannot go that way...\n90H 100M 92V >"


class TestRooms(unittest.TestCase):
    def _walked(self):
        p = JourneyParser()
        p.on_event({"phase": "turn", "n": 1})
        p.on_event({"phase": "tool_call", "name": "look", "args": {}, "id": "t1"})
        p.on_event({"phase": "tool_result", "name": "look",
                    "result": LOOK_TEMPLE, "tool_use_id": "t1"})
        p.on_event({"phase": "tool_call", "name": "move",
                    "args": {"direction": "south"}, "id": "t2"})
        p.on_event({"phase": "tool_result", "name": "move",
                    "result": MOVE_SQUARE, "tool_use_id": "t2"})
        return p

    def test_rooms_position_and_link_from_structured_direction(self):
        state = self._walked().state
        self.assertEqual({"The Temple Of Midgaard", "The Temple Square"},
                         set(state.rooms))
        self.assertEqual("The Temple Square", state.position)
        # The link direction comes from move(direction=...), not from prose.
        self.assertEqual(
            "The Temple Square",
            state.rooms["The Temple Of Midgaard"]["links"]["south"])

    def test_trail_and_frontier(self):
        state = self._walked().state
        self.assertEqual((1, "south", "The Temple Of Midgaard",
                          "The Temple Square"), state.trail[-1])
        # The square's n/e/w exits are untried; temple's s is now linked.
        frontier = dict.fromkeys(d for r, d in state.frontier
                                 if r == "The Temple Square")
        self.assertEqual({"n", "e", "s", "w"}, set(frontier))

    def test_a_failed_move_changes_nothing(self):
        p = self._walked()
        before = p.state.position
        p.on_event({"phase": "tool_call", "name": "move",
                    "args": {"direction": "up"}, "id": "t3"})
        p.on_event({"phase": "tool_result", "name": "move",
                    "result": NOWAY, "tool_use_id": "t3"})
        self.assertEqual(before, p.state.position)

    def test_same_title_different_exits_disambiguates(self):
        p = JourneyParser()
        p.on_tool_call("look", {}, "a")
        p.on_tool_result("look", "Hall\n[ Exits: n ]\n90H 100M 92V >", "a")
        p.on_tool_call("look", {}, "b")
        p.on_tool_result("look", "Hall\n[ Exits: s e ]\n90H 100M 92V >", "b")
        self.assertEqual({"Hall", "Hall (2)"}, set(p.state.rooms))


class TestVitalsAndChar(unittest.TestCase):
    def test_prompt_line_vitals_and_history(self):
        p = JourneyParser()
        p.on_tool_call("look", {}, "t")
        p.on_tool_result("look", LOOK_TEMPLE, "t")
        self.assertEqual(90, p.state.vitals["hp"])
        self.assertEqual(100, p.state.vitals["mana"])
        self.assertEqual(92, p.state.vitals["moves"])
        self.assertEqual([90], p.state.vitals_history)

    def test_score_fills_char_and_max_vitals(self):
        p = JourneyParser()
        p.on_tool_call("check", {"kind": "score"}, "t")
        p.on_tool_result("check", SCORE, "t")
        self.assertEqual(4, p.state.char["level"])
        self.assertEqual(1200, p.state.char["xp"])
        self.assertEqual(340, p.state.char["gold"])
        self.assertEqual(800, p.state.char["xp_to_next"])
        self.assertEqual(100, p.state.vitals["max_hp"])


class TestEvents(unittest.TestCase):
    def test_kill_and_death_are_events_and_death_marks_the_room(self):
        p = JourneyParser()
        p.on_event({"phase": "turn", "n": 3})
        p.on_tool_call("look", {}, "a")
        p.on_tool_result("look", LOOK_TEMPLE, "a")
        p.on_tool_call("attack", {"target": "fido"}, "b")
        p.on_tool_result("attack", KILL, "b")
        p.on_tool_call("attack", {"target": "dragon"}, "c")
        p.on_tool_result("attack", DEATH, "c")
        self.assertIn((3, "killed The beastly fido"), p.state.events)
        self.assertEqual(1, p.state.deaths)
        self.assertIn("death",
                      p.state.rooms["The Temple Of Midgaard"]["hazards"])

    def test_non_mud_text_accumulates_nothing(self):
        # The toy dummy or a filesystem tool: no rooms, no vitals, no crash.
        p = JourneyParser()
        p.on_tool_call("look", {}, "t")
        p.on_tool_result(
            "look", "A sunlit forest clearing. Exits: north, east.", "t")
        self.assertEqual({}, p.state.rooms)
        self.assertIsNone(p.state.vitals["hp"])


class TestFindings(unittest.TestCase):
    def test_blocked_after_repeated_failed_exits(self):
        p = JourneyParser()
        p.on_tool_call("look", {}, "a")
        p.on_tool_result("look", LOOK_TEMPLE, "a")
        for i in range(2):
            p.on_tool_call("move", {"direction": "east"}, f"m{i}")
            p.on_tool_result("move", NOWAY, f"m{i}")
        kinds = {f["kind"]: f for f in p.derive_findings()}
        self.assertIn("blocked", kinds)
        self.assertIn("east failed x2", kinds["blocked"]["detail"])

    def test_confusion_after_repeated_uninformative_looks(self):
        p = JourneyParser()
        for i in range(3):
            p.on_tool_call("look", {}, f"l{i}")
            p.on_tool_result("look", LOOK_TEMPLE, f"l{i}")
        # First look discovers the room (new info); two more do not. One more
        # uninformative look crosses CONFUSION_LOOKS.
        p.on_tool_call("look", {}, "l3")
        p.on_tool_result("look", LOOK_TEMPLE, "l3")
        kinds = [f["kind"] for f in p.derive_findings()]
        self.assertIn("confusion", kinds)

    def test_overpowered_when_a_kill_costs_no_hp(self):
        p = JourneyParser()
        p.on_tool_call("check", {"kind": "score"}, "s")
        p.on_tool_result("check", SCORE, "s")  # max_hp 100, hp 66
        p.on_tool_call("attack", {"target": "fido"}, "a")
        p.on_tool_result("attack", "The beastly fido is dead! R.I.P.\n66H 30M 90V >", "a")
        kinds = {f["kind"] for f in p.derive_findings()}
        self.assertIn("overpowered", kinds)

    def test_death_is_always_a_finding(self):
        p = JourneyParser()
        p.on_tool_call("attack", {"target": "dragon"}, "a")
        p.on_tool_result("attack", DEATH, "a")
        kinds = {f["kind"] for f in p.derive_findings()}
        self.assertIn("death", kinds)
        self.assertIn("underpowered", kinds)


class TestLiveTbamudFormat(unittest.TestCase):
    """Verbatim samples from a REAL live session log (20260725T010753Z),
    ANSI codes and CRLF included, locking the parser to real output."""

    LIVE_MOVE = ("\x1b[0;33mBy The Temple Altar\x1b[0m\r\n"
                 "   You are by the temple altar.\r\n"
                 "\x1b[0;36m[ Exits: n s ]\x1b[0m\r\n\r\n"
                 "24H 100M 85V (news) (motd) > ")

    def test_live_room_with_ansi_and_crlf_parses(self):
        p = JourneyParser()
        p.on_tool_call("tbamud__move", {"direction": "north"}, "m")
        p.on_tool_result("tbamud__move", self.LIVE_MOVE, "m")
        self.assertIn("By The Temple Altar", p.state.rooms)
        self.assertEqual(24, p.state.vitals["hp"])
        self.assertEqual(["n", "s"],
                         p.state.rooms["By The Temple Altar"]["exits"])
