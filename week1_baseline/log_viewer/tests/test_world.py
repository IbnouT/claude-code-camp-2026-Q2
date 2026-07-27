"""The world graph, and the reason it exists at all.

ROOM TITLES DO NOT IDENTIFY ROOMS. Measured in this world: 241 titles are shared by more
than one room and one is shared by forty-one. A trail built from titles folds distinct
places together and draws movements that never happened, which is the whole reason the
map reads the world's own files instead of trusting what the game printed.

The files are DATA, read the way the log is read, so nothing is imported and the boundary
holds. A fixture world is built in the test where the shape matters, and the real files
are used where a real measurement matters, skipped when they are not present so this
suite still passes for someone reading someone else's logs.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from logviewer import world

REAL = world.find_world(Path(__file__).resolve())

#: Two rooms with the SAME TITLE, reachable by different exits from one place. This is
#: the whole problem in five rooms.
FIXTURE = """#100
The Crossroads~
   Roads lead away in every direction.
~
30 cdeh 0
D0
North.
~
~
0 -1 200
D1
East.
~
~
0 -1 300
S
#200
A Hallway~
   A plain hallway.
~
30 cdeh 0
D2
South.
~
~
0 -1 100
S
#300
A Hallway~
   A different hallway that happens to share a name.
~
30 cdeh 0
D3
West.
~
~
0 -1 100
D1
East.
~
~
0 -1 400
S
#400
The Vault~
   The end of the line.
~
30 cdeh 0
S
"""


def _world():
    """The fixture world, parsed from a real file on disk."""
    tmp = TemporaryDirectory()
    (Path(tmp.name) / "test.wld").write_text(FIXTURE, encoding="utf-8")
    return tmp, world.load(tmp.name)


class TestParsingTheWorld(unittest.TestCase):
    def test_rooms_titles_and_exits_come_through(self):
        tmp, rooms = _world()
        self.addCleanup(tmp.cleanup)
        self.assertEqual({100, 200, 300, 400}, set(rooms))
        self.assertEqual("The Crossroads", rooms[100].title)
        self.assertEqual({0: 200, 1: 300}, rooms[100].exits)
        self.assertEqual({}, rooms[400].exits)

    def test_a_missing_world_is_an_empty_one_rather_than_an_error(self):
        # A viewer reading someone else's logs may have no world at all, and the map
        # saying so beats a stack trace.
        with TemporaryDirectory() as tmp:
            self.assertEqual({}, world.load(tmp))
        self.assertEqual({}, world.load("/definitely/not/here"))

    def test_directions_are_in_the_order_the_format_writes_them(self):
        self.assertEqual("north", world.DIRECTIONS[0])
        self.assertEqual("down", world.DIRECTIONS[5])
        self.assertEqual(0, world.BY_NAME["n"])


class TestTitlesCannotIdentifyRoomsAndExitsCan(unittest.TestCase):
    def test_the_fixture_really_does_share_a_title(self):
        # A test about ambiguity over unambiguous data proves nothing.
        tmp, rooms = _world()
        self.addCleanup(tmp.cleanup)
        shared = [v for v, r in rooms.items() if r.title == "A Hallway"]
        self.assertEqual(2, len(shared))

    def test_the_exit_taken_decides_which_room_it_was(self):
        tmp, rooms = _world()
        self.addCleanup(tmp.cleanup)
        # Crossroads, then east. Both hallways are called the same thing, and only one
        # is east of here.
        steps = world.trail([(1, None, "The Crossroads", True),
                             (1, "east", "A Hallway", True)], rooms)
        self.assertEqual(100, steps[0].vnum)
        self.assertEqual(300, steps[1].vnum)
        self.assertTrue(steps[1].disambiguated)

    def test_the_other_exit_reaches_the_other_room_of_the_same_name(self):
        tmp, rooms = _world()
        self.addCleanup(tmp.cleanup)
        steps = world.trail([(1, None, "The Crossroads", True),
                             (1, "north", "A Hallway", True)], rooms)
        self.assertEqual(200, steps[1].vnum)

    def test_a_shared_title_with_no_prior_position_stays_unresolved(self):
        # Guessing one of two would draw a path that did not happen.
        tmp, rooms = _world()
        self.addCleanup(tmp.cleanup)
        steps = world.trail([(1, None, "A Hallway", True)], rooms)
        self.assertIsNone(steps[0].vnum)

    def test_a_refused_move_keeps_the_agent_where_it_was(self):
        tmp, rooms = _world()
        self.addCleanup(tmp.cleanup)
        steps = world.trail([(1, None, "The Crossroads", True),
                             (1, "south", "You cannot go that way.", False),
                             (1, "east", "A Hallway", True)], rooms)
        self.assertEqual(100, steps[1].vnum)
        self.assertTrue(steps[1].blocked)
        # And the next move still resolves from the room it never left.
        self.assertEqual(300, steps[2].vnum)

    def test_colour_codes_do_not_stop_a_title_matching(self):
        # MUD output arrives wrapped in ANSI, and a raw comparison matched nothing at
        # all. Found by running it against a real session.
        tmp, rooms = _world()
        self.addCleanup(tmp.cleanup)
        steps = world.trail([(1, None, "\x1b[0;33mThe Crossroads\x1b[0m", True)], rooms)
        self.assertEqual(100, steps[0].vnum)
        self.assertEqual("The Crossroads", steps[0].title)


class TestTheLayoutPlacesRoomsByCompass(unittest.TestCase):
    def test_walking_north_then_east_places_rooms_accordingly(self):
        tmp, rooms = _world()
        self.addCleanup(tmp.cleanup)
        steps = world.trail([(1, None, "The Crossroads", True),
                             (1, "north", "A Hallway", True)], rooms)
        grid = world.layout(steps, rooms)
        self.assertEqual(2, len(grid))
        # North is up, which is a smaller y.
        self.assertLess(grid[200][1], grid[100][1])

    def test_returning_to_a_room_reuses_its_square(self):
        tmp, rooms = _world()
        self.addCleanup(tmp.cleanup)
        steps = world.trail([(1, None, "The Crossroads", True),
                             (1, "north", "A Hallway", True),
                             (1, "south", "The Crossroads", True)], rooms)
        grid = world.layout(steps, rooms)
        self.assertEqual(2, len(grid), "the same room was placed twice")

    def test_two_rooms_never_share_a_square(self):
        tmp, rooms = _world()
        self.addCleanup(tmp.cleanup)
        steps = world.trail([(1, None, "The Crossroads", True),
                             (1, "east", "A Hallway", True),
                             (1, "east", "The Vault", True)], rooms)
        grid = world.layout(steps, rooms)
        self.assertEqual(len(grid), len(set(grid.values())))

    def test_an_unresolved_step_is_not_placed(self):
        tmp, rooms = _world()
        self.addCleanup(tmp.cleanup)
        steps = world.trail([(1, None, "Somewhere Unknown", True)], rooms)
        self.assertEqual({}, world.layout(steps, rooms))


@unittest.skipIf(REAL is None, "the world files are not present here")
class TestAgainstTheRealWorld(unittest.TestCase):
    """The measurement that justifies the whole module."""

    @classmethod
    def setUpClass(cls):
        cls.rooms = world.load(REAL)

    def test_the_world_is_the_size_it_should_be(self):
        self.assertGreater(len(self.rooms), 1000)

    def test_hundreds_of_titles_are_shared_by_more_than_one_room(self):
        from collections import Counter
        counted = Counter(r.title.lower() for r in self.rooms.values())
        shared = {t: n for t, n in counted.items() if n > 1}
        self.assertGreater(len(shared), 100,
                           "if titles were unique this module would be pointless")
        self.assertGreater(max(shared.values()), 20)

    def test_the_temple_of_midgaard_is_where_it_should_be(self):
        # A named landmark, so a parse that shifted every field by one line fails here
        # rather than producing plausible nonsense.
        temple = self.rooms.get(3001)
        self.assertIsNotNone(temple)
        self.assertEqual("The Temple Of Midgaard", temple.title)
        self.assertEqual(3000, temple.exits[3])
        self.assertEqual(3054, temple.exits[0])

    def test_every_exit_points_at_a_room_that_exists(self):
        dangling = [(r.vnum, target) for r in self.rooms.values()
                    for target in r.exits.values() if target not in self.rooms]
        # A handful across a world this size is ordinary, a majority means the parse is
        # reading the wrong numbers.
        self.assertLess(len(dangling), len(self.rooms) * 0.05,
                        f"{len(dangling)} exits lead nowhere")


@unittest.skipIf(REAL is None, "the world files are not present here")
class TestTheAmbiguityFigureAndItsMethod(unittest.TestCase):
    """The number the docs cite, and how it was counted.

    Case-insensitively, because two rooms whose titles differ only in case are one title
    to a reader and a reader is who the measurement is about. Counted case-sensitively the
    figures come out one lower, which is how the same world produced two different numbers
    and cost somebody a reconciliation.

    Pinned as a RELATIONSHIP rather than as the literal figures, so a world file gaining a
    room does not fail this while the claim still holds.
    """

    @classmethod
    def setUpClass(cls):
        cls.rooms = world.load(REAL)

    def _shared(self, fold_case):
        """Titles used by more than one room, counted with or without folding case."""
        from collections import Counter

        counted = Counter((r.title.lower() if fold_case else r.title)
                          for r in self.rooms.values())
        return {title: n for title, n in counted.items() if n > 1}

    def test_folding_case_finds_at_least_as_many_shared_titles(self):
        loose = self._shared(True)
        strict = self._shared(False)
        self.assertGreaterEqual(len(loose), len(strict))
        self.assertGreaterEqual(max(loose.values()), max(strict.values()))

    def test_the_documented_figures_are_the_case_insensitive_ones(self):
        loose = self._shared(True)
        self.assertEqual(241, len(loose))
        self.assertEqual(41, max(loose.values()))

    def test_and_the_matching_folds_case_the_same_way(self):
        # A measurement counted one way and a lookup done another would be two claims.
        duplicated = [t for t, n in self._shared(True).items() if n > 1]
        self.assertTrue(duplicated)
        steps = world.trail([(1, None, duplicated[0].upper(), True)], self.rooms)
        # An ambiguous title stays unresolved, but it was RECOGNISED as ambiguous rather
        # than missed entirely, which is what folding case buys.
        self.assertIsNone(steps[0].vnum)


if __name__ == "__main__":
    unittest.main()
