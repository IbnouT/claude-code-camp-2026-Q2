"""The pages, tested by parsing what they emit rather than by looking at them.

A renderer can be wrong in ways that still look like a page, so each test here pins one
of them:

- ill-formed markup, which a browser silently recovers from by reparenting content
- an unescaped value, which on a MUD is player-authored text reaching the document
- an external reference, which breaks the page offline and adds a supply chain
- a zero printed where the record held nothing
- a lens that exists in the nav and renders nothing
- a page so large it is complete and unusable, which is not a trade this viewer makes
"""

import json
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

from logviewer import logweb, read, summarize
from logviewer.html import ABSENT, VOID
from logviewer.logview import Record
from logviewer.logweb import LENS_NAMES

FIXTURES = Path(__file__).resolve().parent / "fixtures"
EVERY_PHASE = FIXTURES / "every_phase.jsonl"
LEGACY = FIXTURES / "legacy_step11.jsonl"

#: An src or href pointing at another host or scheme. A page that fetched anything
#: would stop working offline, which is the one environment a log reader must work in.
EXTERNAL = re.compile(r'(?:src|href)\s*=\s*"(?:[a-zA-Z][a-zA-Z0-9+.-]*:|//)')


class _WellFormed(HTMLParser):
    """Fails on a mismatched or unclosed element, which the eye cannot catch."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.open: list[str] = []
        self.problems: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID:
            self.open.append(tag)

    def handle_endtag(self, tag):
        if not self.open:
            self.problems.append(f"</{tag}> with nothing open")
        elif self.open[-1] != tag:
            self.problems.append(f"</{tag}> closes <{self.open[-1]}>")
        else:
            self.open.pop()


def _check(html: str) -> _WellFormed:
    parser = _WellFormed()
    parser.feed(html)
    return parser


def _pages():
    """Every page this viewer can render, over both fixtures."""
    for fixture in (EVERY_PHASE, LEGACY):
        records = read(fixture).records
        summary = summarize(fixture)
        yield f"{fixture.stem}/sessions", logweb.sessions_page([summary])
        for lens in LENS_NAMES:
            yield (f"{fixture.stem}/{lens}",
                   logweb.session_page(records, summary, lens))
        yield f"{fixture.stem}/turn", logweb.turn_page(records, summary, 1)
        yield f"{fixture.stem}/event", logweb.event_page(records, summary, 1)
    left, right = read(EVERY_PHASE).records, read(LEGACY).records
    yield "diff", logweb.diff_page(left, right, summarize(EVERY_PHASE),
                                   summarize(LEGACY))
    yield "empty sessions", logweb.sessions_page([])


class TestEveryPageIsWellFormedAndSelfContained(unittest.TestCase):
    def test_there_are_pages_to_check(self):
        # A structural test that silently checks nothing is worse than none.
        self.assertGreaterEqual(len(list(_pages())), 18)

    def test_no_page_is_ill_formed(self):
        for name, html in _pages():
            with self.subTest(page=name):
                parsed = _check(html)
                self.assertEqual([], parsed.problems)
                self.assertEqual([], parsed.open, "elements left open")

    def test_no_page_fetches_anything(self):
        for name, html in _pages():
            with self.subTest(page=name):
                self.assertEqual([], EXTERNAL.findall(html))

    def test_every_page_declares_its_document_and_title(self):
        for name, html in _pages():
            with self.subTest(page=name):
                self.assertTrue(html.startswith("<!doctype html>"))
                self.assertIn("<title>", html)
                self.assertIn('lang="en"', html)

    def test_both_themes_are_styled_and_the_toggle_wins(self):
        _name, html = next(iter(_pages()))
        self.assertIn("prefers-color-scheme: dark", html)
        self.assertIn(':root[data-theme="dark"]', html)
        self.assertIn(':root[data-theme="light"]', html)


class TestNothingReachesThePageUnescaped(unittest.TestCase):
    """A MUD carries player-authored text and a tool result can hold anything."""

    HOSTILE = '<img src=x onerror="alert(1)">'

    def _records(self, **overrides):
        base = [
            Record("session_start", {"phase": "session_start", "schema": 1,
                                     "model": self.HOSTILE,
                                     "system": self.HOSTILE}, 1),
            Record("turn", {"phase": "turn", "n": 1}, 2),
            Record("prompt", {"phase": "prompt", "message_count": 1,
                              "messages": [{"role": "user",
                                            "content": self.HOSTILE}],
                              "tools": [self.HOSTILE], "tool_count": 1}, 3),
            Record("tool_call", {"phase": "tool_call", "name": self.HOSTILE,
                                 "args": {"target": self.HOSTILE},
                                 "id": "t1"}, 4),
            Record("tool_result", {"phase": "tool_result", "name": self.HOSTILE,
                                   "result": self.HOSTILE, "ok": False,
                                   "error": self.HOSTILE,
                                   "tool_use_id": "t1"}, 5),
            Record("response", {"phase": "response", "text": self.HOSTILE,
                                "usage": {"input_tokens": 10, "output_tokens": 2},
                                "duration_ms": 100, "input_tokens": 10}, 6),
            Record("turn_end", {"phase": "turn_end", "reason": "completed",
                                "iterations": 1, "tokens": 12}, 7),
        ]
        return base

    def test_no_lens_lets_a_tag_through(self):
        records = self._records()
        summary = summarize(EVERY_PHASE)
        for lens in LENS_NAMES:
            with self.subTest(lens=lens):
                html = logweb.session_page(records, summary, lens)
                self.assertNotIn("<img src=x", html)
                self.assertIn("&lt;img", html)

    def test_the_turn_page_escapes_a_hostile_tool_result(self):
        html = logweb.turn_page(self._records(), summarize(EVERY_PHASE), 1)
        self.assertNotIn("<img src=x", html)
        self.assertNotIn('onerror="alert(1)"', html)

    def test_ansi_colours_survive_without_becoming_an_injection_path(self):
        records = self._records()
        records[4] = Record("tool_result", {
            "phase": "tool_result", "name": "look",
            "result": "\x1b[36m<b>The Temple</b>\x1b[0m", "ok": True,
            "tool_use_id": "t1"}, 5)
        html = logweb.turn_page(records, summarize(EVERY_PHASE), 1)
        self.assertIn('class="c-cyan"', html)
        self.assertIn("&lt;b&gt;The Temple&lt;/b&gt;", html)
        self.assertNotIn("<b>The Temple</b>", html)


class TestAbsentIsRenderedAsAbsent(unittest.TestCase):
    def test_an_unpriced_session_never_shows_a_zero_for_its_cost(self):
        records = [
            Record("session_start", {"phase": "session_start", "schema": 1}, 1),
            Record("turn", {"phase": "turn", "n": 1}, 2),
            Record("response", {"phase": "response", "text": "hi"}, 3),
            Record("turn_end", {"phase": "turn_end", "reason": "completed",
                                "iterations": 1}, 4),
        ]
        html = logweb.session_page(records, summarize(LEGACY), "narrative")
        self.assertIn(ABSENT, html)
        self.assertNotIn("$0.0000", html)

    def test_a_legacy_session_says_amplification_is_not_recorded(self):
        html = logweb.session_page(read(LEGACY).records, summarize(LEGACY))
        self.assertIn("not recorded", html)

    def test_the_diff_marks_a_field_one_side_lacks(self):
        html = logweb.diff_page(read(EVERY_PHASE).records, read(LEGACY).records,
                                summarize(EVERY_PHASE), summarize(LEGACY))
        self.assertIn("not recorded", html)


class TestEveryLensRendersSomething(unittest.TestCase):
    def test_every_lens_is_offered_and_each_is_a_url(self):
        # Not a fixed count. Lenses are ADDITIVE by direction, so a test asserting
        # exactly seven would fail every time the viewer gained an angle, which is the
        # opposite of what it should protect.
        html = logweb.session_page(read(EVERY_PHASE).records,
                                   summarize(EVERY_PHASE))
        summary = summarize(EVERY_PHASE)
        for lens in LENS_NAMES:
            with self.subTest(lens=lens):
                self.assertIn(f'href="/s/{summary.id}/{lens}"', html)
        self.assertGreaterEqual(len(LENS_NAMES), 7)

    def test_no_lens_was_removed_when_the_new_ones_arrived(self):
        """The direction is enrich, never remove.

        Every angle that has ever been reachable stays reachable, so this names the
        original seven explicitly rather than counting.
        """
        for lens in ("narrative", "timeline", "context", "tools", "journey", "errors",
                     "raw"):
            with self.subTest(lens=lens):
                self.assertIn(lens, LENS_NAMES)

    def test_the_current_lens_is_marked_for_a_screen_reader_too(self):
        summary = summarize(EVERY_PHASE)
        html = logweb.session_page(read(EVERY_PHASE).records, summary, "tools")
        self.assertIn(f'href="/s/{summary.id}/tools" title="grouped by tool rather '
                      f'than by time" aria-current="page"', html)

    def test_a_lens_with_nothing_to_show_says_so_rather_than_rendering_blank(self):
        # A session of one untimed call has no timeline and no journey. Both have to
        # say that, since an empty panel reads as a broken page.
        records = [
            Record("session_start", {"phase": "session_start", "schema": 1}, 1),
            Record("turn", {"phase": "turn", "n": 1}, 2),
            Record("response", {"phase": "response", "text": "hi"}, 3),
            Record("turn_end", {"phase": "turn_end", "reason": "completed",
                                "iterations": 1}, 4),
        ]
        summary = summarize(LEGACY)
        for lens, expected in (("timeline", "no timeline"),
                               ("journey", "no journey"),
                               ("tools", "No tool call"),
                               ("errors", "Nothing failed")):
            with self.subTest(lens=lens):
                html = logweb.session_page(records, summary, lens)
                self.assertIn(expected, html)

    def test_an_unknown_lens_falls_back_rather_than_erroring(self):
        html = logweb.session_page(read(EVERY_PHASE).records,
                                   summarize(EVERY_PHASE), "nonsense")
        self.assertIn("WHAT STANDS OUT", html)


class TestFindingsLeadAndLinkToTheirTurn(unittest.TestCase):
    def test_each_finding_links_to_its_turns_own_page(self):
        # Not an anchor. An anchor exists on the narrative lens only, so a jump from
        # the timeline or the tools lens landed nowhere.
        summary = summarize(EVERY_PHASE)
        for lens in LENS_NAMES:
            with self.subTest(lens=lens):
                html = logweb.session_page(read(EVERY_PHASE).records, summary, lens)
                self.assertIn("WHAT STANDS OUT", html)
                self.assertIn(f'href="/s/{summary.id}/turn/1"', html)

    def test_the_instruction_is_the_title(self):
        # How a person recognises a run is what they asked for, not its category.
        html = logweb.session_page(read(EVERY_PHASE).records,
                                   summarize(EVERY_PHASE))
        self.assertIn("<title>find the menu at the bakery</title>", html)

    def test_a_clean_session_says_why_it_is_quiet(self):
        records = [
            Record("session_start", {"phase": "session_start", "schema": 1}, 1),
            Record("turn", {"phase": "turn", "n": 1}, 2),
            Record("response", {"phase": "response", "text": "hi",
                                "duration_ms": 100}, 3),
            Record("turn_end", {"phase": "turn_end", "reason": "completed",
                                "iterations": 1}, 4),
        ]
        html = logweb.session_page(records, summarize(LEGACY))
        self.assertIn("too few", html)


class TestTheRawLensIsCompleteAndUsable(unittest.TestCase):
    """Complete and unusable is not a trade this viewer gets to make.

    Rendering every body inline produced a 32MB page on a real session, because a
    prompt payload carries the whole conversation and there are hundreds of them. Paged,
    with the long bodies one click away on their own URL, it is both.
    """

    def _many(self, count):
        records = [Record("session_start", {"phase": "session_start", "schema": 1}, 1)]
        for index in range(count):
            records.append(Record("prompt", {
                "phase": "prompt", "message_count": 1,
                "messages": [{"role": "user", "content": "x" * 9000}],
                "tools": [], "tool_count": 0}, index + 2))
        return records

    def test_a_page_holds_at_most_the_stated_number_of_events(self):
        records = self._many(400)
        html = logweb.session_page(records, summarize(EVERY_PHASE), "raw", 1)
        self.assertEqual(logweb.RAW_PAGE, html.count('class="leg"')
                         + html.count('class="leg broken"'))
        self.assertIn(f"events 1 to {logweb.RAW_PAGE} of 401", html)

    def test_a_long_body_is_truncated_with_the_whole_record_one_click_away(self):
        summary = summarize(EVERY_PHASE)
        html = logweb.session_page(self._many(3), summary, "raw", 1)
        self.assertIn(f'href="/s/{summary.id}/event/2"', html)
        self.assertIn("the whole record", html)
        # Truncated, so the page cannot be the sum of every payload.
        self.assertLess(len(html), 200_000)

    def test_the_whole_record_really_is_on_its_own_page(self):
        records = self._many(3)
        html = logweb.event_page(records, summarize(EVERY_PHASE), 2)
        self.assertIn("x" * 9000, html)

    def test_a_page_number_past_the_end_clamps_rather_than_emptying(self):
        html = logweb.session_page(self._many(10), summarize(EVERY_PHASE),
                                   "raw", 999)
        self.assertIn("events 1 to 11 of 11", html)

    def test_a_line_that_does_not_exist_says_so(self):
        html = logweb.event_page(self._many(3), summarize(EVERY_PHASE), 9999)
        self.assertIn("no event on line 9999", html)

    def test_every_event_is_reachable_across_the_pages(self):
        records = self._many(400)
        summary = summarize(EVERY_PHASE)
        seen = set()
        page_number = 1
        while True:
            html = logweb.session_page(records, summary, "raw", page_number)
            seen.update(int(n) for n in re.findall(r'/event/(\d+)"', html))
            if "later →" not in html:
                break
            page_number += 1
            self.assertLess(page_number, 20, "paging did not terminate")
        self.assertEqual({r.line for r in records[1:]}, seen)


class TestTheSessionListAnswersWhichRun(unittest.TestCase):
    def test_it_states_the_absence_when_there_are_no_logs(self):
        html = logweb.sessions_page([])
        self.assertIn("No session logs found", html)

    def test_a_no_turn_session_reports_no_turns_and_no_cost(self):
        html = logweb.sessions_page([summarize(FIXTURES / "every_phase.jsonl")])
        self.assertIn("<td", html)
        self.assertNotIn("$0.0000", html)

    def test_each_row_links_to_its_session(self):
        summary = summarize(EVERY_PHASE)
        html = logweb.sessions_page([summary])
        self.assertIn(f'href="/s/{summary.id}"', html)


class TestALegCarriesOnlyItsOwnIteration(unittest.TestCase):
    """Found by looking at a real turn, not by any test that existed.

    The turn page rendered each response against the WHOLE turn's records, so every leg
    listed every tool call the turn made. On a twenty-one call turn that meant opening
    iteration six and reading twenty calls belonging to other legs. It looked right,
    which is why nothing caught it.
    """

    def _two_iterations(self):
        return [
            Record("session_start", {"phase": "session_start", "schema": 1}, 1),
            Record("turn", {"phase": "turn", "n": 1}, 2),
            Record("iteration", {"phase": "iteration", "n": 1, "max": 25}, 3),
            Record("plan", {"phase": "plan", "text": "FIRST PLAN"}, 4),
            Record("response", {"phase": "response", "text": "FIRST REPLY",
                                "duration_ms": 100}, 5),
            Record("tool_call", {"phase": "tool_call", "name": "mud__north",
                                 "args": {}, "id": "a"}, 6),
            Record("tool_result", {"phase": "tool_result", "name": "mud__north",
                                   "result": "FIRST RESULT", "ok": True,
                                   "tool_use_id": "a"}, 7),
            Record("iteration", {"phase": "iteration", "n": 2, "max": 25}, 8),
            Record("plan", {"phase": "plan", "text": "SECOND PLAN"}, 9),
            Record("response", {"phase": "response", "text": "SECOND REPLY",
                                "duration_ms": 100}, 10),
            Record("tool_call", {"phase": "tool_call", "name": "mud__south",
                                 "args": {}, "id": "b"}, 11),
            Record("tool_result", {"phase": "tool_result", "name": "mud__south",
                                   "result": "SECOND RESULT", "ok": True,
                                   "tool_use_id": "b"}, 12),
            Record("turn_end", {"phase": "turn_end", "reason": "completed",
                                "iterations": 2, "tokens": 100}, 13),
        ]

    def _legs(self, html):
        """The body of each leg, split so one leg's content cannot leak into another."""
        return re.findall(r'<div class="legbody">(.*?)</div></details>', html,
                          re.DOTALL)

    def test_each_leg_shows_its_own_call_and_result(self):
        html = logweb.turn_page(self._two_iterations(), summarize(EVERY_PHASE), 1)
        bodies = self._legs(html)
        self.assertEqual(2, len(bodies), f"expected two legs, got {len(bodies)}")
        first, second = bodies
        self.assertIn("mud__north", first)
        self.assertIn("FIRST RESULT", first)
        self.assertNotIn("mud__south", first)
        self.assertNotIn("SECOND RESULT", first)
        self.assertIn("mud__south", second)
        self.assertNotIn("mud__north", second)

    def test_each_leg_shows_its_own_plan(self):
        bodies = self._legs(logweb.turn_page(self._two_iterations(),
                                             summarize(EVERY_PHASE), 1))
        self.assertIn("FIRST PLAN", bodies[0])
        self.assertNotIn("SECOND PLAN", bodies[0])
        self.assertIn("SECOND PLAN", bodies[1])

    def test_a_turn_with_no_iteration_markers_still_renders_its_legs(self):
        # An older log, or a turn the writer cut short. Dropping the leg because it
        # could not be attributed would lose part of the record.
        records = [r for r in self._two_iterations() if r.phase != "iteration"]
        html = logweb.turn_page(records, summarize(EVERY_PHASE), 1)
        self.assertEqual(2, len(self._legs(html)))

    def test_a_real_turn_renders_each_call_exactly_once(self):
        # The arithmetic that makes the bug obvious: seven calls across seven legs
        # rendered forty-nine times before the fix, and seven after.
        records = read(LEGACY).records
        html = logweb.turn_page(records, summarize(LEGACY), 1)
        calls = sum(1 for r in records if r.phase == "tool_call")
        self.assertGreater(calls, 1, "the fixture needs more than one call to prove it")
        self.assertEqual(calls, html.count("<h3>tool call</h3>"))


class TestATurnIsAddressedByPositionNotByItsRecordedNumber(unittest.TestCase):
    """Found by driving the running viewer, which is the only way it could be.

    `/retry` and `/undo` step the turn counter back, so a redone turn keeps the number
    it had and a log can legitimately carry four turns all labelled 3. The viewer
    resolved `/turn/<n>` by the recorded number, so it reached the first and silently
    hid the rest, and dropped the forward link that would have exposed them.

    On the sessions here that hid three turns and BOTH compaction records in the entire
    corpus, which is why the compaction leg had never once been seen on screen.
    """

    def _redone(self):
        """Six turns, four of them recorded as turn 3, as one real session is."""
        out = [Record("session_start", {"phase": "session_start", "schema": 1}, 1)]
        line = 2
        for position, recorded in enumerate([1, 2, 3, 3, 3, 3], start=1):
            out.append(Record("turn", {"phase": "turn", "n": recorded}, line))
            out.append(Record("iteration", {"phase": "iteration", "n": 1}, line + 1))
            out.append(Record("response", {"phase": "response",
                                           "text": f"reply from position {position}",
                                           "duration_ms": 100}, line + 2))
            if position in (5, 6):
                out.append(Record("compaction", {
                    "phase": "compaction", "before": 7594, "dropped": 0,
                    "compressed": 15, "summarized": True,
                    "over_budget": False}, line + 3))
            out.append(Record("turn_end", {"phase": "turn_end",
                                           "reason": "completed",
                                           "iterations": 1}, line + 4))
            line += 5
        return out

    def test_every_turn_is_reachable(self):
        records = self._redone()
        summary = summarize(EVERY_PHASE)
        for position in range(1, 7):
            with self.subTest(position=position):
                html = logweb.turn_page(records, summary, position)
                self.assertNotIn("there is no turn", html)
                self.assertIn(f"reply from position {position}", html)

    def test_a_redone_turn_says_the_log_calls_it_something_else(self):
        html = logweb.turn_page(self._redone(), summarize(EVERY_PHASE), 4)
        self.assertIn("logged as turn 3", html)
        # This fixture is an OLDER log with no attempt field, so the page says the
        # number was reused without claiming to know it was deliberate.
        self.assertIn("did not record whether the reuse was deliberate", html)

    def test_a_log_that_records_the_attempt_says_it_was_deliberate(self):
        records = self._redone()
        for record in records:
            if record.phase == "turn" and record.get("n") == 3:
                record.data["attempt"] = 2
        html = logweb.turn_page(records, summarize(EVERY_PHASE), 4)
        self.assertIn("attempt 2 at turn 3", html)
        self.assertIn("/retry or /undo", html)

    def test_a_turn_whose_number_matches_its_position_says_nothing_extra(self):
        html = logweb.turn_page(self._redone(), summarize(EVERY_PHASE), 2)
        self.assertNotIn("logged as turn", html)

    def test_the_forward_link_survives_a_repeated_number(self):
        # This is what hid the later turns: asking whether a turn NUMBERED n+1 exists
        # removed the only link that would have led to them.
        summary = summarize(EVERY_PHASE)
        html = logweb.turn_page(self._redone(), summary, 4)
        self.assertIn(f'href="/s/{summary.id}/turn/5"', html)
        self.assertIn(f'href="/s/{summary.id}/turn/3"', html)

    def test_the_strip_and_the_narrative_link_to_positions(self):
        summary = summarize(EVERY_PHASE)
        html = logweb.session_page(self._redone(), summary, "narrative")
        for position in range(1, 7):
            with self.subTest(position=position):
                self.assertIn(f'href="/s/{summary.id}/turn/{position}"', html)

    def test_the_compaction_legs_are_reachable_at_last(self):
        summary = summarize(EVERY_PHASE)
        found = 0
        for position in range(1, 7):
            html = logweb.turn_page(self._redone(), summary, position)
            found += html.count('k-compaction">compaction')
        self.assertEqual(2, found, "a compaction leg is still unreachable")


class TestALegAndAFigureNameThemselves(unittest.TestCase):
    def _turn(self, **turn_end):
        return [
            Record("session_start", {"phase": "session_start", "schema": 1}, 1),
            Record("turn", {"phase": "turn", "n": 1}, 2),
            Record("iteration", {"phase": "iteration", "n": 1}, 3),
            Record("response", {"phase": "response", "text": "a"}, 4),
            Record("response", {"phase": "response", "text": "wound down"}, 5),
            Record("turn_end", {"phase": "turn_end", "reason": "max_tokens",
                                "iterations": 1, **turn_end}, 6),
        ]

    def test_an_absent_figure_says_which_field_is_absent(self):
        # The header read "· · unavailable ·", so a reader could see something was
        # missing and not what.
        html = logweb.turn_page(self._turn(), summarize(EVERY_PHASE), 1)
        self.assertIn("took", html)
        self.assertIn("cost", html)
        self.assertIn("volume", html)

    def test_the_wind_down_call_is_not_a_second_leg_of_the_same_name(self):
        html = logweb.turn_page(self._turn(), summarize(EVERY_PHASE), 1)
        labels = re.findall(r'<span class="mono">((?:iteration|wind-down)[^<]*)', html)
        self.assertEqual(len(labels), len(set(labels)), f"duplicated labels: {labels}")
        self.assertIn("wind-down after iteration 1", labels)

    def test_counts_read_as_english(self):
        html = logweb.turn_page(self._turn(), summarize(EVERY_PHASE), 1)
        self.assertIn("1 iteration ", html)
        self.assertNotIn("1 iterations", html)


class TestACompactionSaysWhatItDid(unittest.TestCase):
    """A compaction that compressed fifteen results read as "dropping 0 messages"."""

    def _with(self, **fields):
        base = {"phase": "compaction", "before": 7594, "dropped": 0,
                "compressed": 0, "summarized": False, "over_budget": False}
        return [
            Record("session_start", {"phase": "session_start", "schema": 1}, 1),
            Record("turn", {"phase": "turn", "n": 1}, 2),
            Record("iteration", {"phase": "iteration", "n": 1}, 3),
            Record("compaction", {**base, **fields}, 4),
            Record("response", {"phase": "response", "text": "a"}, 5),
            Record("turn_end", {"phase": "turn_end", "reason": "completed",
                                "iterations": 1}, 6),
        ]

    def test_compressing_without_dropping_is_not_reported_as_nothing(self):
        html = logweb.turn_page(self._with(compressed=15, summarized=True),
                                summarize(EVERY_PHASE), 1)
        self.assertIn("compressed 15 tool results", html)
        self.assertIn("kept a journey note", html)
        self.assertNotIn("dropped 0 messages", html)

    def test_it_states_what_it_started_from(self):
        html = logweb.turn_page(self._with(compressed=15), summarize(EVERY_PHASE), 1)
        self.assertIn("from 7,594 tokens", html)

    def test_a_compaction_that_did_nothing_says_so(self):
        html = logweb.turn_page(self._with(), summarize(EVERY_PHASE), 1)
        self.assertIn("changed nothing", html)

    def test_still_over_budget_is_shouted_because_it_is_the_bad_case(self):
        html = logweb.turn_page(self._with(dropped=4, over_budget=True),
                                summarize(EVERY_PHASE), 1)
        self.assertIn("STILL over budget", html)

    def test_the_finding_says_the_same_thing_as_the_leg(self):
        from logviewer import findings
        found = [f for f in findings(self._with(compressed=15, summarized=True))
                 if f.kind == "context"]
        self.assertEqual(1, len(found))
        self.assertIn("compressing 15 tool results", found[0].headline)
        self.assertNotIn("dropping 0", found[0].headline)


class TestTheControlsAreVisibleRatherThanLearned(unittest.TestCase):
    """Ibnou's question was the right one: why does a browser need those keys.

    It mostly did not. `j`/`k` duplicated scrolling and `o`/`c` duplicated clicking a
    disclosure triangle, and the browser does both without being taught. Only two things
    are beyond it, searching this record and jumping to the next failure, so only those
    two are bound and both are also buttons that say what they do.
    """

    def _turn_page(self):
        return logweb.turn_page(read(EVERY_PHASE).records, summarize(EVERY_PHASE), 1)

    def test_the_redundant_bindings_are_gone(self):
        html = self._turn_page()
        for key in ('event.key === "j"', 'event.key === "k"',
                    'event.key === "o"', 'event.key === "c"'):
            with self.subTest(key=key):
                self.assertNotIn(key, html)

    def test_the_two_the_browser_cannot_do_are_bound(self):
        html = self._turn_page()
        self.assertIn('event.key === "/"', html)
        self.assertIn('event.key === "f"', html)

    def test_each_is_also_a_button_that_says_what_it_does(self):
        html = self._turn_page()
        self.assertIn('id="expand"', html)
        self.assertIn("Expand all", html)
        self.assertIn('id="nextfail"', html)
        self.assertIn("Next failure", html)

    def test_the_key_legend_is_gone_because_the_controls_are_visible(self):
        html = self._turn_page()
        self.assertNotIn("next and previous leg", html)
        self.assertNotIn("open and close all", html)

    def test_the_first_keypress_after_a_load_is_not_swallowed(self):
        # The handler is on the document, so until something has focus a keypress goes
        # nowhere. The first press was silently lost, which reads as broken.
        self.assertIn("document.body.focus()", self._turn_page())


class TestNextFailureLandsOnWhatRealLogsContain(unittest.TestCase):
    """No session on disk has a failed tool result.

    Every real failure in the whole corpus is a retry or a tripped ceiling, so a jump
    that only looked for failed tool calls had nothing to land on in any real log. A
    control that works in tests and never in use is not a working control.
    """

    def _with(self, phase, **fields):
        return [
            Record("session_start", {"phase": "session_start", "schema": 1}, 1),
            Record("turn", {"phase": "turn", "n": 1}, 2),
            Record("iteration", {"phase": "iteration", "n": 1}, 3),
            Record(phase, {"phase": phase, **fields}, 4),
            Record("response", {"phase": "response", "text": "a",
                                "duration_ms": 100}, 5),
            Record("turn_end", {"phase": "turn_end", "reason": "completed",
                                "iterations": 1}, 6),
        ]

    def test_a_retry_is_reachable_by_next_failure(self):
        html = logweb.turn_page(self._with("retry", attempt=1, wait=0.5, status=529),
                                summarize(EVERY_PHASE), 1)
        self.assertIn('class="leg broken"', html)

    def test_a_tripped_ceiling_is_reachable_too(self):
        html = logweb.turn_page(
            self._with("limit_reached", kind="max_tokens", n=66283, max=60000),
            summarize(EVERY_PHASE), 1)
        self.assertIn('class="leg broken"', html)

    def test_a_compaction_is_notable_rather_than_broken(self):
        # It is not a failure, and putting it in the failure jump would send a reader
        # to something that went right.
        html = logweb.turn_page(
            self._with("compaction", before=1000, dropped=4, compressed=0,
                       summarized=False, over_budget=False, context_window=200_000),
            summarize(EVERY_PHASE), 1)
        self.assertIn('class="leg marked"', html)
        self.assertNotIn('class="leg broken"', html)

    def test_every_real_session_with_trouble_has_something_to_jump_to(self):
        # The measurement that exposed this: the corpus has no failed tool result at all.
        import glob
        checked = 0
        for path in sorted(glob.glob("../../.boukensha/sessions/*.jsonl")):
            records = read(path).records
            if not any(r.trouble for r in records):
                continue
            summary = summarize(path)
            positions = {t.position for t in __import__(
                "logviewer").group_turns(records)}
            reachable = any('class="leg broken"'
                            in logweb.turn_page(records, summary, position)
                            for position in positions)
            self.assertTrue(reachable, f"{summary.id} has trouble but nothing to jump to")
            checked += 1
        self.assertGreater(checked, 0, "no session with trouble was checked")


class TestAQuietCardCollapses(unittest.TestCase):
    def test_a_card_with_no_figures_says_so_in_one_line(self):
        # Four rows reading "total ·", "median call ·", "slowest ·" took a quarter of
        # the page to say nothing.
        records = [
            Record("session_start", {"phase": "session_start", "schema": 1}, 1),
            Record("turn", {"phase": "turn", "n": 1}, 2),
            Record("response", {"phase": "response", "text": "a"}, 3),
            Record("turn_end", {"phase": "turn_end", "reason": "completed",
                                "iterations": 1}, 4),
        ]
        html = logweb.session_page(records, summarize(LEGACY))
        self.assertIn("card quiet", html)
        self.assertIn("none of which recorded a duration", html)
        self.assertNotIn("median call", html)

    def test_a_card_with_figures_stays_open(self):
        html = logweb.session_page(read(EVERY_PHASE).records, summarize(EVERY_PHASE))
        self.assertIn("median call", html)


class TestContentIsNotSmallerThanTheTextNobodyReads(unittest.TestCase):
    """Body was 15px and twenty of twenty-four sizes were below 1rem.

    The one element at a comfortable size was the one nobody reads, and every element
    carrying data was shrunk below it. Small is for LABELS.

    Asserted as a PROPERTY rather than as literal declarations. An earlier version of
    this matched exact CSS strings, so it failed the moment the page was redesigned while
    the property it cared about still held. A test that breaks on a rewrite it should
    survive is testing the implementation.
    """

    #: Selectors whose content a reader came for. None of these may be under 1rem.
    CONTENT = ("body", "table", ".sub", ".kv", "pre", ".timeline .t", "nav.lenses a",
               'input[type="search"]', "button.tool", ".barlabel")

    #: Selectors that are labels, where small is correct.
    LABELS = (".eyebrow", "th", ".chip", ".crumb", "kbd", ".hint", ".legbody h3",
              "footer.foot", "ol.findings .detail", "svg.map text",
              "svg.pressure text")

    def _rules(self):
        """Each selector block in the stylesheet, as (selector, body)."""
        from logviewer.style import CSS
        return re.findall(r"([^{}]+)\{([^{}]*)\}", CSS)

    def _smallest(self, selector):
        """The smallest rem size any rule for this selector sets, or None."""
        sizes = []
        for selectors, body in self._rules():
            names = [s.strip() for s in selectors.split(",")]
            if selector not in names:
                continue
            for value in re.findall(r"(\d*\.?\d+)rem", body):
                # Only sizes, not spacing: a font shorthand or a font-size.
                pass
            for match in re.finditer(r"font(?:-size)?\s*:([^;]*)", body):
                for value in re.findall(r"(\d*\.?\d+)rem", match.group(1)):
                    sizes.append(float(value))
        return min(sizes) if sizes else None

    def test_the_selectors_being_checked_actually_exist(self):
        # A property test over selectors the stylesheet does not define passes and means
        # nothing, which is the failure mode of every structural test.
        from logviewer.style import CSS
        for selector in self.CONTENT + self.LABELS:
            with self.subTest(selector=selector):
                self.assertIn(selector, CSS)

    def test_nothing_carrying_data_is_smaller_than_the_body_text(self):
        problems = {}
        for selector in self.CONTENT:
            smallest = self._smallest(selector)
            if smallest is not None and smallest < 1.0:
                problems[selector] = smallest
        self.assertEqual({}, problems,
                         f"content set below 1rem: {problems}")

    def test_the_body_size_is_comfortable(self):
        from logviewer.style import CSS
        match = re.search(r"body\s*\{[^}]*font:\s*(\d+)px", CSS)
        self.assertIsNotNone(match, "the body size is not set in px")
        self.assertGreaterEqual(int(match.group(1)), 16)

    def test_labels_are_allowed_to_be_small_and_most_of_them_are(self):
        # The distinction is the point: small exists, and it is for labels.
        small = [s for s in self.LABELS
                 if (self._smallest(s) or 1.0) < 1.0]
        self.assertGreaterEqual(len(small), 5,
                                "labels are not distinguished from content at all")

    def test_the_terminal_block_is_capped_so_it_cannot_own_the_viewport(self):
        from logviewer.style import CSS
        match = re.search(r"pre\.term\s*\{[^}]*max-height:\s*(\d+)em", CSS)
        self.assertIsNotNone(match, "the terminal block has no height cap")
        self.assertLessEqual(int(match.group(1)), 30)

    def test_the_terminal_is_a_panel_rather_than_a_hole_in_the_page(self):
        """It stays a terminal, because MUD output should read like the game.

        What changed is the contrast: a near-black block on a light page was the only
        high-contrast element, so the eye landed on game text rather than on the figures
        the page was opened for. Asserted as a distance from black rather than as a hex
        value, so a future palette change is free as long as the property holds.
        """
        from logviewer.style import CSS
        match = re.search(r'--term-bg:\s*#([0-9a-fA-F]{6})', CSS)
        self.assertIsNotNone(match)
        value = match.group(1)
        channels = [int(value[i:i + 2], 16) for i in (0, 2, 4)]
        self.assertGreater(sum(channels) / 3, 20,
                           "the terminal block is near-black again")


class TestThePageNeverPromisesAKeyItDoesNotBind(unittest.TestCase):
    """Deleting a behaviour includes deleting every promise of it.

    Three times in two days a document described behaviour the code no longer had: a plan
    sentence citing a stale test count, a claim about what the plan recorded, and this
    file's own requirement still promising `j`, `k`, `o` and `c` after they were removed.
    Remembering to grep is not a mechanism, so this is one: every key the page OFFERS to a
    reader must be a key the page BINDS, and every key it binds must be offered.

    That makes the two halves of the promise fail together rather than drifting apart.
    """

    #: A shortcut the page shows to a reader, as `<kbd>x</kbd>`.
    OFFERED = re.compile(r"<kbd>([^<]{1,12})</kbd>")
    #: A shortcut the page actually handles.
    BOUND = re.compile(r'event\.key === "([^"]+)"')

    def _pages_with_controls(self):
        records = read(EVERY_PHASE).records
        summary = summarize(EVERY_PHASE)
        yield "turn", logweb.turn_page(records, summary, 1)
        for lens in ("tools", "context", "raw"):
            yield lens, logweb.session_page(records, summary, lens)

    def test_every_key_offered_is_a_key_bound(self):
        for name, html in self._pages_with_controls():
            with self.subTest(page=name):
                offered = {k.strip() for k in self.OFFERED.findall(html)}
                bound = set(self.BOUND.findall(html))
                self.assertTrue(offered, "no shortcut is offered at all")
                self.assertEqual(set(), offered - bound,
                                 f"offered and not bound: {sorted(offered - bound)}")

    def test_every_key_bound_is_a_key_offered(self):
        # The other direction, so a shortcut cannot exist that only the source knows
        # about. Escape is excluded: it clears a focused field, which is a convention
        # rather than a feature, and advertising it would be noise.
        for name, html in self._pages_with_controls():
            with self.subTest(page=name):
                offered = {k.strip() for k in self.OFFERED.findall(html)}
                bound = set(self.BOUND.findall(html)) - {"Escape"}
                self.assertEqual(set(), bound - offered,
                                 f"bound and not offered: {sorted(bound - offered)}")

    def test_no_page_describes_a_behaviour_that_was_removed(self):
        gone = ("next and previous leg", "open and close all", "previous leg",
                "without reaching for a mouse")
        for name, html in self._pages_with_controls():
            for phrase in gone:
                with self.subTest(page=name, phrase=phrase):
                    self.assertNotIn(phrase, html)


class TestTheThreeNewLensesRenderRealAngles(unittest.TestCase):
    """Additive: three angles arrived and nothing that was reachable stopped being so."""

    def test_the_map_says_so_when_the_world_is_not_available(self):
        """A viewer reading someone else's logs has no world.

        Exercised through the documented override rather than by patching a function.
        An earlier version monkeypatched `world.load` and passed alone while failing in
        the full suite, which is a test whose result depends on what ran before it. The
        env var is the real mechanism and cannot be defeated by import aliasing.
        """
        import os
        from tempfile import TemporaryDirectory

        from logviewer.world import WORLD_ENV

        with TemporaryDirectory() as empty:
            previous = os.environ.get(WORLD_ENV)
            os.environ[WORLD_ENV] = empty
            try:
                html = logweb.session_page(read(EVERY_PHASE).records,
                                           summarize(EVERY_PHASE), "map")
            finally:
                if previous is None:
                    os.environ.pop(WORLD_ENV, None)
                else:
                    os.environ[WORLD_ENV] = previous
        self.assertIn("world files are not available", html)
        self.assertIn("BOUKENSHA_WORLD", html)

    def test_the_player_lens_shows_the_thresholds_it_used(self):
        html = logweb.session_page(read(EVERY_PHASE).records,
                                   summarize(EVERY_PHASE), "player")
        self.assertIn("HOW EACH IS DECIDED", html)
        for word in ("confused", "blocked", "bored", "stuck", "overpowered", "drained"):
            with self.subTest(word=word):
                self.assertIn(word, html)

    def test_the_pressure_lens_draws_the_data_not_the_limit(self):
        """A 200,000 window and a 7,600 peak drew a flat line and a distant rule.

        Complete, useless, and it said the window was large rather than anything about
        the session. So the axis follows the data, and the window is stated as a figure
        when the data does not come near it.
        """
        records = [
            Record("session_start", {"phase": "session_start", "schema": 1}, 1),
            Record("turn", {"phase": "turn", "n": 1}, 2),
            Record("response", {"phase": "response", "text": "a",
                                "input_tokens": 7600,
                                "context_window": 200_000}, 3),
            Record("response", {"phase": "response", "text": "b",
                                "input_tokens": 7000,
                                "context_window": 200_000}, 4),
            Record("turn_end", {"phase": "turn_end", "reason": "completed",
                                "iterations": 2}, 5),
        ]
        html = logweb.session_page(records, summarize(EVERY_PHASE), "pressure")
        self.assertIn("not drawn to scale against it", html)
        self.assertIn("peak 7.6k", html)
        # The window rule is not drawn, because drawing it is what flattened the data.
        self.assertNotIn('class="limit"', html)

    def test_and_it_does_draw_the_window_when_the_data_reaches_it(self):
        records = [
            Record("session_start", {"phase": "session_start", "schema": 1}, 1),
            Record("turn", {"phase": "turn", "n": 1}, 2),
            Record("response", {"phase": "response", "text": "a",
                                "input_tokens": 900, "context_window": 1000}, 3),
            Record("response", {"phase": "response", "text": "b",
                                "input_tokens": 950, "context_window": 1000}, 4),
            Record("turn_end", {"phase": "turn_end", "reason": "completed",
                                "iterations": 2}, 5),
        ]
        html = logweb.session_page(records, summarize(EVERY_PHASE), "pressure")
        self.assertIn('class="limit"', html)
        self.assertIn("compacts at", html)

    def test_a_manual_compaction_is_named_as_asked_for(self):
        # Otherwise a compaction at four percent of the window reads as a broken
        # threshold, which is what it looked like on a real session.
        records = [
            Record("session_start", {"phase": "session_start", "schema": 1}, 1),
            Record("turn", {"phase": "turn", "n": 1}, 2),
            Record("response", {"phase": "response", "text": "a",
                                "input_tokens": 7600,
                                "context_window": 200_000}, 3),
            Record("compaction", {"phase": "compaction", "before": 7594,
                                  "dropped": 0, "compressed": 15,
                                  "summarized": True, "over_budget": False,
                                  "context_window": 200_000,
                                  "trigger": "manual"}, 4),
            Record("response", {"phase": "response", "text": "b",
                                "input_tokens": 3000,
                                "context_window": 200_000}, 5),
            Record("turn_end", {"phase": "turn_end", "reason": "completed",
                                "iterations": 2}, 6),
        ]
        html = logweb.session_page(records, summarize(EVERY_PHASE), "pressure")
        self.assertIn("ASKED FOR", html)
        self.assertIn("asked for", html)
        self.assertIn("compressed 15 tool results", html)

    def test_a_compaction_with_nothing_left_says_that_rather_than_zero(self):
        records = [
            Record("session_start", {"phase": "session_start", "schema": 1}, 1),
            Record("turn", {"phase": "turn", "n": 1}, 2),
            Record("response", {"phase": "response", "text": "a",
                                "input_tokens": 100, "context_window": 1000}, 3),
            Record("compaction", {"phase": "compaction", "before": 0, "dropped": 0,
                                  "compressed": 0, "summarized": False,
                                  "over_budget": False,
                                  "context_window": 1000}, 4),
            Record("turn_end", {"phase": "turn_end", "reason": "completed",
                                "iterations": 1}, 5),
        ]
        html = logweb.session_page(records, summarize(EVERY_PHASE), "pressure")
        self.assertIn("nothing left to compact", html)


if __name__ == "__main__":
    unittest.main()
