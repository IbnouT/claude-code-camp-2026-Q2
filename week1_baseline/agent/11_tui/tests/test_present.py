"""The presenter: events become readable beats, plumbing never does.

These are framework-free unit tests (no Textual): the presenter is the boundary
that keeps the raw trace out of the TUI, so the key assertions are that room /
action / thinking beats are produced and that prompt / iteration / response /
token events produce nothing.
"""

import unittest

from boukensha.journey import Presenter, humanize_action, strip_ansi

LOOK = ("\x1b[0;33mThe Temple Of Midgaard\x1b[0m\r\n"
        "   A grand marble hall.\r\n"
        "\x1b[0;36m[ Exits: n e s w ]\x1b[0m\r\n"
        "24H 100M 85V (news) (motd) > ")


class TestHumanize(unittest.TestCase):
    def test_prefix_and_json_are_stripped_to_a_phrase(self):
        self.assertEqual("move west",
                         humanize_action("tbamud__move", {"direction": "w"}))
        self.assertEqual("move north",
                         humanize_action("tbamud__move", {"direction": "north"}))
        self.assertEqual("look", humanize_action("tbamud__look", {}))
        self.assertEqual("attack the fido",
                         humanize_action("tbamud__attack", {"target": "fido"}))
        self.assertEqual("examine meat",
                         humanize_action("tbamud__examine", {"target": "meat"}))

    def test_unknown_tool_still_reads_cleanly(self):
        # No prefix, no JSON braces, just verb plus the one argument value.
        self.assertEqual("cast fireball",
                         humanize_action("tbamud__cast", {"spell": "fireball"}))
        self.assertEqual("rest", humanize_action("rest", {}))


class TestDeNoiseBoundary(unittest.TestCase):
    def test_plumbing_events_produce_no_cards(self):
        p = Presenter()
        for phase in ("turn", "iteration", "prompt", "response", "turn_end",
                      "compaction", "retry", "limit_reached"):
            self.assertEqual([], p.on_event({"phase": phase, "n": 1}),
                             f"{phase} must not become a card")
        self.assertEqual([], p.cards)

    def test_room_action_thinking_are_the_only_beats(self):
        p = Presenter()
        p.on_event({"phase": "tool_call", "name": "tbamud__look",
                    "args": {}, "id": "a"})
        p.on_event({"phase": "tool_result", "name": "tbamud__look",
                    "result": LOOK, "tool_use_id": "a"})
        p.on_event({"phase": "reasoning", "text": "I should head north."})
        kinds = [c.kind for c in p.cards]
        self.assertEqual(["action", "room", "thinking"], kinds)


class TestRoomCard(unittest.TestCase):
    def test_room_parses_title_exits_and_clean_body(self):
        p = Presenter()
        p.on_event({"phase": "tool_call", "name": "tbamud__look",
                    "args": {}, "id": "a"})
        p.on_event({"phase": "tool_result", "name": "tbamud__look",
                    "result": LOOK, "tool_use_id": "a"})
        room = p.current_room
        self.assertEqual("The Temple Of Midgaard", room.title)
        self.assertEqual(["n", "e", "s", "w"], room.exits)
        self.assertIn("grand marble hall", room.body)
        # The game-prompt telemetry line never leaks into the body.
        self.assertNotIn("100M", room.body)
        self.assertNotIn("\x1b", room.body)

    def test_non_room_result_is_a_transient_message_not_a_card(self):
        p = Presenter()
        p.on_event({"phase": "tool_call", "name": "tbamud__examine",
                    "args": {"target": "meat"}, "id": "b"})
        cards = p.on_event({"phase": "tool_result", "name": "tbamud__examine",
                            "result": "You do not see that here.\r\n"
                            "24H 100M 78V > ", "tool_use_id": "b"})
        self.assertEqual([], cards)              # no room card
        self.assertIn("You do not see that here", p.latest_message)


class TestRecentAndReply(unittest.TestCase):
    def test_recent_actions_keep_only_the_last_three(self):
        p = Presenter()
        for i, d in enumerate(["n", "e", "s", "w"]):
            p.on_event({"phase": "tool_call", "name": "tbamud__move",
                        "args": {"direction": d}, "id": f"m{i}"})
        bodies = [c.body for c in p.recent_actions]
        self.assertEqual(3, len(bodies))
        self.assertEqual(["-> move east", "-> move south", "-> move west"], bodies)

    def test_reply_text_becomes_the_current_thinking(self):
        p = Presenter()
        p.add_reply("\x1b[0mI have found the temple and will head north.")
        self.assertIsNotNone(p.current_thinking)
        self.assertIn("head north", p.current_thinking.body)
        self.assertNotIn("\x1b", p.current_thinking.body)


class TestLineStructurePreserved(unittest.TestCase):
    # Regression: cleaning used to collapse every newline into a space, so a
    # markdown table or a shop list became one unreadable run-on line, and the
    # game-prompt telemetry leaked into non-room messages.
    def test_reply_table_keeps_its_rows(self):
        p = Presenter()
        p.add_reply("Here is the menu:\n\n| Item | Cost |\n|---|---|\n"
                    "| bread | 14 |\n| waybread | 70 |")
        body = p.current_thinking.body
        self.assertIn("\n", body)                       # not a single line
        self.assertIn("| Item | Cost |", body)
        self.assertIn("| bread | 14 |", body)

    def test_shop_list_keeps_lines_and_drops_the_prompt(self):
        p = Presenter()
        p.on_event({"phase": "tool_call", "name": "tbamud__list",
                    "args": {}, "id": "s"})
        p.on_event({"phase": "tool_result", "name": "tbamud__list", "result":
                    "## Available\r\n 1) A danish pastry 7\r\n 2) A bread 14\r\n"
                    "24H 100M 69V (news) (motd) > ", "tool_use_id": "s"})
        msg = p.latest_message
        self.assertIn("1) A danish pastry 7", msg)
        self.assertIn("2) A bread 14", msg)
        self.assertEqual(3, len(msg.splitlines()))      # header + two items
        self.assertNotIn("100M", msg)                   # prompt telemetry gone


class TestCombat(unittest.TestCase):
    ROOMFIGHT = ("Main Street\r\nA busy street.\r\n"
                 "The beastly fido is here, fighting YOU!\r\n"
                 "[ Exits: n s ]\r\n24H 100M 74V > ")
    R1 = "You swing your fist at the beastly fido, but miss him!\r\n91H 100M 51V > "
    KILL = ("You pierce the beastly fido extremely hard.\r\n"
            "The beastly fido is dead! R.I.P.\r\n"
            "You receive 70 experience points.\r\n91H 100M 51V > ")

    def _result(self, p, name, result, cid, args=None):
        p.on_event({"phase": "tool_call", "name": name, "args": args or {}, "id": cid})
        return p.on_event({"phase": "tool_result", "name": name,
                           "result": result, "tool_use_id": cid})

    def test_room_starts_combat_without_dumping_the_description(self):
        p = Presenter()
        self._result(p, "tbamud__look", self.ROOMFIGHT, "r")
        self.assertTrue(p.combat_active)
        # Only the fighting line is captured, not "A busy street."
        self.assertEqual(["The beastly fido is here, fighting YOU!"],
                         p.combat_lines)

    def test_attack_rounds_accumulate_the_blow_by_blow(self):
        p = Presenter()
        self._result(p, "tbamud__attack", self.R1, "a", {"target": "fido"})
        self.assertTrue(p.combat_active)
        self.assertIn("You swing your fist at the beastly fido, but miss him!",
                      p.combat_lines)

    def test_kill_ends_combat_with_victory_and_a_feed_card(self):
        p = Presenter()
        self._result(p, "tbamud__attack", self.R1, "a", {"target": "fido"})
        cards = self._result(p, "tbamud__attack", self.KILL, "k", {"target": "fido"})
        self.assertFalse(p.combat_active)
        self.assertEqual("Victory over the beastly fido", p.combat_result)
        self.assertEqual(["combat"], [c.kind for c in cards])

    def test_death_ends_combat_defeated(self):
        p = Presenter()
        cards = self._result(p, "tbamud__attack",
                             "The massive Minotaur hits you.\r\nYou are dead! "
                             "Sorry...\r\n", "d", {"target": "minotaur"})
        self.assertFalse(p.combat_active)
        self.assertEqual("You were defeated", p.combat_result)
        self.assertEqual(["combat"], [c.kind for c in cards])

    def test_moving_to_a_peaceful_room_retires_the_box(self):
        p = Presenter()
        self._result(p, "tbamud__attack", self.KILL, "k", {"target": "fido"})
        self.assertTrue(p.combat_lines)            # victory box still up
        self._result(p, "tbamud__move",
                     "Market Square\r\nA quiet square.\r\n[ Exits: s ]\r\n"
                     "91H 100M 50V > ", "m", {"direction": "n"})
        self.assertEqual([], p.combat_lines)
        self.assertIsNone(p.combat_result)

    def test_a_disconnect_menu_ends_the_fight_without_leaking(self):
        # The live bug: losing/disconnecting returned the tbaMUD login menu,
        # which used to stay stuck as "IN COMBAT" with the menu in the box.
        p = Presenter()
        self._result(p, "tbamud__attack", self.R1, "a", {"target": "fido"})
        self.assertTrue(p.combat_active)
        menu = ("That's not a menu choice!\r\nWelcome to tbaMUD!\r\n"
                "0) Exit from tbaMUD.\r\n1) Enter the game.\r\n")
        self._result(p, "tbamud__attack", menu, "b", {"target": "fido"})
        self.assertFalse(p.combat_active)          # fight is over: pulse stops
        self.assertEqual([], p.combat_lines)       # box retired
        self.assertFalse(any("tbaMUD" in ln or "menu choice" in ln
                             for ln in p.combat_lines))


class TestThinkingStaysCurrent(unittest.TestCase):
    # The live bug: the thinking pane kept showing the bakery summary after the
    # agent had moved on to fighting. Thinking now tracks the agent's latest
    # text (response commentary + final summary), and skips the tool-use
    # placeholder so a tool-only turn does not blank it.
    def test_thinking_follows_the_agents_latest_text(self):
        p = Presenter()
        p.on_event({"phase": "response", "text": "Found the bakery: bread 14 gold."})
        self.assertIn("bakery", p.current_thinking.body)
        p.on_event({"phase": "response", "text": "(tool use: 1 call)"})
        self.assertIn("bakery", p.current_thinking.body)     # placeholder skipped
        p.on_event({"phase": "response", "text": "Heading to the West Gate for Fido."})
        self.assertIn("West Gate", p.current_thinking.body)   # no longer stale

    def test_identical_text_is_not_duplicated(self):
        p = Presenter()
        p.on_event({"phase": "response", "text": "Victory is mine."})
        p.add_reply("Victory is mine.")          # same words via the routed reply
        self.assertEqual(1, sum(c.kind == "thinking" for c in p.cards))


class TestStripAnsi(unittest.TestCase):
    def test_escapes_are_removed(self):
        self.assertEqual("Poor Alley",
                         strip_ansi("\x1b[0;33mPoor Alley\x1b[0m"))


if __name__ == "__main__":
    unittest.main()
