"""What stands out, and the ways a viewer can lie while looking right.

Every test here guards a specific way of being plausibly wrong:

- calling an ordinary turn unusual because the session was too small to have a median
- reporting a cached session's window as nearly empty, which is the exact defect the
  agent had to fix and the reader can reintroduce for free
- multiplying tokens by a per-million rate without the divisor, which overstates by a
  million and still looks like money
- treating an absent field as a zero, so an unpriced session reads as free

Fixtures are built in the test where the shape matters, and read from the checked-in
logs where a real record matters.
"""

import unittest
from pathlib import Path

from logviewer import (
    CIRCLING, GRINDING, MIN_SAMPLE, PER, Distribution, attribution, cache_saving,
    call_durations, journey_findings, pressure_series, why_no_journey,
    cost_cause, diff, findings, prompt_occupancy, read, repetition, rooms_seen,
    turn_activity,
    why_nothing_stands_out, window_pressure,
)
from logviewer.logview import Record

FIXTURES = Path(__file__).resolve().parent / "fixtures"
EVERY_PHASE = FIXTURES / "every_phase.jsonl"
LEGACY = FIXTURES / "legacy_step11.jsonl"


def _rec(phase, **data):
    return Record(phase=phase, data={"phase": phase, **data}, line=0)


def _session(turns):
    """A session of ``turns``, each ``(cost, [call_ms, ...])``."""
    out = [_rec("session_start", schema=1)]
    for number, (cost, calls) in enumerate(turns, start=1):
        out.append(_rec("turn", n=number))
        for ms in calls:
            out.append(_rec("response", text="x", input_tokens=100,
                            output_tokens=10, duration_ms=ms))
        out.append(_rec("turn_end", reason="completed", iterations=len(calls),
                        tokens=110 * len(calls), cost_usd=cost))
    return out


class TestOutliersAreRelativeAndHonestlySilent(unittest.TestCase):
    def test_a_session_too_small_for_a_median_calls_nothing_unusual(self):
        # Two turns, one ten times the other. Tempting to flag, and wrong to: two
        # values are not a distribution.
        records = _session([(0.01, [100]), (0.10, [1000])])
        self.assertEqual([], [f for f in findings(records) if f.kind in ("cost", "time")])

    def test_and_it_says_which_kind_of_silence_that_is(self):
        quiet = why_nothing_stands_out(_session([(0.01, [100]), (0.10, [1000])]))
        self.assertIn("too few", quiet)
        clean = why_nothing_stands_out(_session([(0.01, [100])] * 5))
        self.assertIn("no failures", clean)
        self.assertEqual("no turns ran, so there is nothing to compare",
                         why_nothing_stands_out([_rec("session_start", schema=1)]))

    def test_with_enough_turns_the_outlier_is_named_against_the_median(self):
        records = _session([(0.01, [100]), (0.01, [100]), (0.01, [100]),
                            (0.50, [100])])
        costs = [f for f in findings(records) if f.kind == "cost"]
        self.assertEqual(1, len(costs))
        self.assertEqual(4, costs[0].turn)
        self.assertIn("50.0x the median turn", costs[0].headline)

    def test_an_expensive_session_does_not_flag_all_of_itself(self):
        # Every turn costs a lot and none is unusual FOR THIS SESSION. A fixed
        # threshold would flag all four and tell the reader nothing.
        records = _session([(5.0, [100])] * 4)
        self.assertEqual([], [f for f in findings(records) if f.kind == "cost"])

    def test_the_sample_floor_is_the_one_the_module_states(self):
        below = Distribution([1.0] * (MIN_SAMPLE - 1))
        at = Distribution([1.0] * MIN_SAMPLE)
        self.assertFalse(below.enough)
        self.assertTrue(at.enough)
        self.assertFalse(below.is_outlier(1000.0))

    def test_findings_lead_with_what_broke(self):
        records = _session([(0.01, [100])] * 3)
        records.insert(-1, _rec("tool_result", name="move", ok=False,
                                error="blocked"))
        records.insert(-1, _rec("retry", attempt=1, wait=0.5, status=529))
        kinds = [f.kind for f in findings(records)]
        self.assertEqual("failure", kinds[0])
        self.assertEqual("retry", kinds[1])

    def test_every_finding_says_where_to_look(self):
        records = read(EVERY_PHASE).records
        found = findings(records)
        self.assertTrue(found)
        for finding in found:
            self.assertIsNotNone(finding.turn, f"{finding.kind} has no turn")


class TestWindowOccupancyCountsCachedTokens(unittest.TestCase):
    """Caching changes a token's price, never its presence.

    Reading occupancy from `input_tokens` alone understates a cached prompt, because on
    some providers that figure excludes the cached portion. Measured on a real session:
    4,045 read that way against 33,171 counted properly, an eightfold error that makes
    a full window look nearly empty.
    """

    def test_the_cached_classes_are_added_to_the_fresh_ones(self):
        record = _rec("response", input_tokens=120,
                      usage={"input_tokens": 120,
                             "cache_read_input_tokens": 9000,
                             "cache_creation_input_tokens": 380})
        self.assertEqual(9500, prompt_occupancy(record))

    def test_a_provider_that_already_includes_them_is_not_double_counted(self):
        record = _rec("response", usage={"prompt_tokens": 9500,
                                         "cached_tokens": 9000})
        self.assertEqual(9500, prompt_occupancy(record))

    def test_a_log_with_no_nested_usage_falls_back_to_the_flat_count(self):
        self.assertEqual(4000, prompt_occupancy(_rec("response",
                                                     input_tokens=4000)))

    def test_the_session_peak_uses_it(self):
        records = [
            _rec("session_start", schema=1), _rec("turn", n=1),
            _rec("response", input_tokens=500, context_window=200_000,
                 usage={"input_tokens": 500, "cache_read_input_tokens": 9000}),
            _rec("turn_end", reason="completed", iterations=1),
        ]
        self.assertEqual(9500, window_pressure(records)["peak_prompt"])


class TestTheCounterfactualIsReadNotInvented(unittest.TestCase):
    def test_it_abstains_when_the_session_recorded_no_rates(self):
        result = cache_saving(read(LEGACY).records)
        self.assertFalse(result["available"])
        self.assertIn("no per-class usage", result["why"])

    def test_it_abstains_rather_than_owning_a_price_table(self):
        records = [
            _rec("session_start", schema=1), _rec("turn", n=1),
            _rec("response", input_tokens=100,
                 usage={"input_tokens": 100, "cache_read_input_tokens": 900}),
            _rec("turn_end", reason="completed", iterations=1,
                 usage={"fresh_input": 100, "cache_read": 900,
                        "cache_write": 0, "output": 10}),
        ]
        result = cache_saving(records)
        self.assertFalse(result["available"])
        self.assertIn("owns no price table", result["why"])

    def test_rates_are_per_million_and_the_divisor_is_not_dropped(self):
        # This one bit for real. Tokens times a per-million rate without the divisor
        # overstates by a factor of a million and still reads as a plausible dollar
        # figure, so the unit is pinned rather than trusted.
        records = [
            _rec("session_start", schema=1,
                 rates={"input": 1.0, "output": 5.0, "cache_read": 0.1}),
            _rec("turn", n=1),
            _rec("response", input_tokens=100,
                 usage={"input_tokens": 100, "cache_read_input_tokens": 1_000_000}),
            _rec("turn_end", reason="completed", iterations=1,
                 usage={"fresh_input": 100, "cache_read": 1_000_000,
                        "cache_write": 0, "output": 10}),
        ]
        result = cache_saving(records)
        self.assertTrue(result["available"])
        # A million cached tokens at $1.00 per million, paid at $0.10 per million.
        self.assertAlmostEqual(1.0, result["as_if_uncached"], places=9)
        self.assertAlmostEqual(0.1, result["actually_paid"], places=9)
        self.assertAlmostEqual(0.9, result["saved"], places=9)
        self.assertEqual(1_000_000, PER)

    def test_it_computes_on_the_real_fixture(self):
        result = cache_saving(read(EVERY_PHASE).records)
        self.assertTrue(result["available"], result.get("why"))
        self.assertGreater(result["saved"], 0)
        # It saved something, and less than the whole session cost, which is the only
        # sanity bound available without re-deriving the bill.
        self.assertLess(result["saved"], attribution(read(EVERY_PHASE).records)["total"])

    def test_repetition_reports_the_share_from_the_classes(self):
        share = repetition(read(EVERY_PHASE).records)
        self.assertTrue(share["available"])
        self.assertEqual(share["prompt_tokens"],
                         share["fresh_input"] + share["cache_read"]
                         + share["cache_write"])
        self.assertGreater(share["cached_share"], 0)


class TestAbsentIsNeverZero(unittest.TestCase):
    def test_an_unpriced_turn_is_counted_as_unpriced_not_as_free(self):
        records = _session([(None, [100]), (0.01, [100])])
        figures = attribution(records)
        self.assertEqual(1, figures["unpriced_turns"])
        # The priced turn's cost is the total, and the unpriced one adds nothing
        # rather than adding a zero.
        self.assertEqual(0.01, figures["total"])

    def test_the_total_says_which_records_it_came_from(self):
        # Per-call figures are the finest the writer records, so they win. A log
        # carrying cost only on its turns still reports a total, because a page
        # showing a price on every turn and "unavailable" in its header would be
        # disagreeing with itself.
        by_turn = attribution(_session([(0.01, [100])] * 2))
        self.assertEqual("turns", by_turn["total_from"])
        by_call = attribution(read(EVERY_PHASE).records)
        self.assertEqual("calls", by_call["total_from"])

    def test_a_session_with_no_cost_anywhere_reports_none(self):
        self.assertIsNone(attribution(_session([(None, [100])]))["total"])
        self.assertIsNone(attribution(_session([(None, [100])]))["total_from"])

    def test_a_turn_with_no_cost_is_not_the_largest(self):
        records = _session([(None, [100])])
        self.assertIsNone(attribution(records)["largest_turn"])

    def test_amplification_absent_says_so_rather_than_reading_zero(self):
        figures = attribution(read(LEGACY).records)
        self.assertIsNone(figures["amplification"])
        self.assertFalse(figures["amplification_available"])

    def test_an_untimed_call_is_skipped_not_counted_as_instant(self):
        records = [_rec("session_start", schema=1), _rec("turn", n=1),
                   _rec("response", text="a", duration_ms=1000),
                   _rec("response", text="b"),
                   _rec("turn_end", reason="completed", iterations=2)]
        self.assertEqual([1000.0], call_durations(records).values)


class TestTheTurnStripReadsBeforeAnyTurnIsOpened(unittest.TestCase):
    def test_activity_names_what_the_agent_did(self):
        rows = turn_activity(read(EVERY_PHASE).records)
        self.assertEqual(1, len(rows))
        self.assertIn("ping", rows[0]["activity"])
        self.assertTrue(rows[0]["tripped"])

    def test_a_long_turn_is_summarised_with_a_count_of_the_rest(self):
        records = [_rec("session_start", schema=1), _rec("turn", n=1)]
        for i in range(9):
            records.append(_rec("tool_call", name=f"mud__move{i}",
                                args={"direction": "north"}))
        records.append(_rec("turn_end", reason="completed", iterations=9))
        activity = turn_activity(records)[0]["activity"]
        self.assertIn("+4 more", activity)
        # The server prefix is stripped, since it is the same on every line.
        self.assertNotIn("mud__", activity)

    def test_a_turn_with_no_tool_calls_has_an_empty_activity_not_a_placeholder(self):
        records = _session([(0.01, [100])])
        self.assertEqual("", turn_activity(records)[0]["activity"])


class TestTheDiffReportsMissingAsMissing(unittest.TestCase):
    def test_a_field_one_side_lacks_is_not_recorded_rather_than_zero(self):
        rows = {r["field"]: r for r in diff(read(EVERY_PHASE).records,
                                            read(LEGACY).records)}
        self.assertEqual("not recorded", rows["amplification"]["change"])

    def test_a_changed_model_is_called_out(self):
        left = [_rec("session_start", schema=1, model="a"), _rec("turn", n=1),
                _rec("turn_end", reason="completed", iterations=1)]
        right = [_rec("session_start", schema=1, model="b"), _rec("turn", n=1),
                 _rec("turn_end", reason="completed", iterations=1)]
        rows = {r["field"]: r for r in diff(left, right)}
        self.assertEqual("different", rows["model"]["change"])

    def test_a_numeric_change_reports_direction_and_size(self):
        rows = {r["field"]: r for r in diff(_session([(0.01, [100])] * 4),
                                            _session([(0.01, [100])] * 1))}
        self.assertEqual("-75%", rows["turns"]["change"])


class TestCauseIsLinkedToEffectOrLeftAlone(unittest.TestCase):
    """One of the four answers: not what a turn cost, but why.

    Both causes a reader can act on are in the record: more calls, or more history
    carried per call. Anything beyond that would be a guess, and a plausible guess is
    worse than silence because it stops the reader looking for the real cause.
    """

    def _turn(self, number, calls, prompt, cost):
        out = [_rec("turn", n=number)]
        for _ in range(calls):
            out.append(_rec("response", text="x", input_tokens=prompt,
                            output_tokens=10, duration_ms=100))
        out.append(_rec("turn_end", reason="completed", iterations=calls,
                        cost_usd=cost))
        return out

    def test_a_rise_names_the_call_count_and_the_history_behind_it(self):
        records = ([_rec("session_start", schema=1)]
                   + self._turn(1, 5, 1000, 0.01)
                   + self._turn(2, 20, 6000, 0.10))
        rows = cost_cause(records)
        self.assertIsNone(rows[0]["cause"])
        self.assertIn("20 calls against 5", rows[1]["cause"])
        self.assertIn("6,000 against 1,000", rows[1]["cause"])
        self.assertIn("10.0x turn 1", rows[1]["cause"])

    def test_ordinary_variation_gets_no_explanation(self):
        records = ([_rec("session_start", schema=1)]
                   + self._turn(1, 5, 1000, 0.010)
                   + self._turn(2, 5, 1000, 0.011))
        self.assertIsNone(cost_cause(records)[1]["cause"])

    def test_a_rise_with_no_cause_in_the_record_says_nothing(self):
        # Same calls, same history, more money. The record does not explain it, so
        # neither does this.
        records = ([_rec("session_start", schema=1)]
                   + self._turn(1, 5, 1000, 0.01)
                   + self._turn(2, 5, 1000, 0.50))
        self.assertIsNone(cost_cause(records)[1]["cause"])

    def test_an_unpriced_turn_is_not_compared(self):
        records = ([_rec("session_start", schema=1)]
                   + self._turn(1, 5, 1000, None)
                   + self._turn(2, 20, 6000, 0.10))
        self.assertIsNone(cost_cause(records)[1]["cause"])


class TestProgressPerTokenOrAnHonestRefusal(unittest.TestCase):
    def test_a_session_with_no_room_headings_says_so_rather_than_zero(self):
        records = _session([(0.01, [100])])
        result = rooms_seen(records)
        self.assertFalse(result["available"])
        self.assertIn("no progress measure", result["why"])

    def test_headings_are_counted_distinctly_and_visits_separately(self):
        records = [_rec("session_start", schema=1), _rec("turn", n=1)]
        for heading in ("The Temple Square", "On The Bridge", "The Temple Square"):
            records.append(_rec("tool_result", name="move", ok=True,
                                result=f"{heading}\nYou are standing here."))
        records.append(_rec("response", text="x", input_tokens=100,
                            output_tokens=10, cost_usd=0.02))
        records.append(_rec("turn_end", reason="completed", iterations=1))
        result = rooms_seen(records)
        self.assertEqual(2, result["headings"])
        self.assertEqual(3, result["visits"])

    def test_prose_and_a_refusal_are_not_counted_as_places(self):
        records = [_rec("session_start", schema=1), _rec("turn", n=1),
                   _rec("tool_result", name="move", ok=True,
                        result="You cannot go that way."),
                   _rec("tool_result", name="move", ok=False,
                        result="The Temple Square\nblocked"),
                   _rec("turn_end", reason="completed", iterations=1)]
        # The first ends in a full stop, the second failed. Neither is a place reached.
        self.assertFalse(rooms_seen(records)["available"])

    def test_it_reports_cost_each_only_when_the_session_was_priced(self):
        records = [_rec("session_start", schema=1), _rec("turn", n=1),
                   _rec("tool_result", name="move", ok=True,
                        result="The Temple Square\nYou are here"),
                   _rec("response", text="x", input_tokens=100, output_tokens=10),
                   _rec("turn_end", reason="completed", iterations=1)]
        result = rooms_seen(records)
        self.assertTrue(result["available"])
        self.assertIsNone(result["cost_each"])


class TestThePlayerFindingsAreComputedNotGuessed(unittest.TestCase):
    """The four words of the project's brief, decided by counts a reader can argue with.

    This is the lens the project exists for. Everything else reports what the RUN did and
    this reports what the PLAYER experienced, so each finding names the count behind it
    rather than asserting a mood.
    """

    def _play(self, actions):
        """A session of (tool, args, what the world said, ok)."""
        out = [_rec("session_start", schema=1), _rec("turn", n=1)]
        for index, (tool, args, said, ok) in enumerate(actions):
            out.append(_rec("tool_call", name=f"mud__{tool}", args=args,
                            id=f"t{index}"))
            out.append(_rec("tool_result", name=f"mud__{tool}", result=said, ok=ok,
                            tool_use_id=f"t{index}"))
        out.append(_rec("turn_end", reason="completed", iterations=1))
        return out

    def test_a_session_with_no_mud_tools_reports_nothing_and_says_why(self):
        records = _session([(0.01, [100])])
        self.assertEqual([], journey_findings(records))
        self.assertIn("not MUD tools", why_no_journey(records))

    def test_circling_the_same_room_reads_as_confused(self):
        actions = [("move", {"direction": "north"}, "The Temple Square\nhere", True)
                   ] * CIRCLING
        found = {f.word: f for f in journey_findings(self._play(actions))}
        self.assertIn("confused", found)
        self.assertIn(f"{CIRCLING} times", found["confused"].headline)
        self.assertIn("The Temple Square", found["confused"].headline)

    def test_two_visits_are_not_yet_circling(self):
        actions = [("move", {"direction": "north"}, "The Temple Square\nhere", True)] * 2
        self.assertNotIn("confused",
                         {f.word for f in journey_findings(self._play(actions))})

    def test_a_repeated_refusal_reads_as_blocked(self):
        actions = [("move", {"direction": "north"}, "You cannot go that way.", False)] * 3
        found = {f.word: f for f in journey_findings(self._play(actions))}
        self.assertIn("blocked", found)
        self.assertIn("3 times", found["blocked"].headline)

    def test_a_long_identical_run_reads_as_bored(self):
        actions = [("move", {"direction": "north"}, f"Room {i}\nhere", True)
                   for i in range(GRINDING)]
        # Same tool and same arguments, different rooms, so it is not circling.
        found = {f.word: f for f in journey_findings(self._play(actions))}
        self.assertIn("bored", found)
        self.assertIn(f"{GRINDING} identical", found["bored"].headline)

    def test_a_level_gate_reads_as_overpowered(self):
        actions = [("move", {"direction": "north"},
                    "This zone is above your recommended level.", True)] * 4
        found = {f.word: f for f in journey_findings(self._play(actions))}
        self.assertIn("overpowered", found)
        self.assertIn("4 times", found["overpowered"].headline)

    def test_a_level_gate_is_not_counted_as_a_room(self):
        # It ends in a full stop and is a message, not a place. Counting it as a room
        # made a level gate read as going in circles, which is the wrong finding from
        # the right data.
        actions = [("move", {"direction": "north"},
                    "This zone is above your recommended level.", True)] * 4
        found = {f.word for f in journey_findings(self._play(actions))}
        self.assertNotIn("confused", found)

    def test_running_out_of_movement_reads_as_drained(self):
        actions = [("move", {"direction": "north"}, "You are too exhausted.", True)]
        found = {f.word: f for f in journey_findings(self._play(actions))}
        self.assertIn("drained", found)
        self.assertIn("exhausted", found["drained"].headline)

    def test_every_finding_carries_the_evidence_that_produced_it(self):
        actions = ([("move", {"direction": "north"}, "The Temple Square\nhere", True)]
                   * CIRCLING)
        for finding in journey_findings(self._play(actions)):
            with self.subTest(word=finding.word):
                self.assertTrue(finding.evidence,
                                "a finding without evidence is a mood, not a report")


class TestPressureIsDrawnFromTheRecord(unittest.TestCase):
    def test_a_session_with_no_usage_says_so(self):
        records = [_rec("session_start", schema=1), _rec("turn", n=1),
                   _rec("turn_end", reason="completed", iterations=1)]
        result = pressure_series(records)
        self.assertFalse(result["available"])
        self.assertIn("no pressure to draw", result["why"])

    def test_the_series_counts_every_input_class(self):
        records = [
            _rec("session_start", schema=1), _rec("turn", n=1),
            _rec("response", text="a", input_tokens=100, context_window=200_000,
                 usage={"input_tokens": 100, "cache_read_input_tokens": 9000}),
            _rec("turn_end", reason="completed", iterations=1),
        ]
        result = pressure_series(records)
        self.assertEqual(9100, result["points"][0]["prompt"])
        self.assertEqual(9100, result["peak"])

    def test_a_compaction_is_placed_and_carries_its_reason(self):
        records = [
            _rec("session_start", schema=1), _rec("turn", n=1),
            _rec("response", text="a", input_tokens=100, context_window=1000),
            _rec("compaction", before=900, dropped=4, compressed=0, summarized=False,
                 over_budget=False, context_window=1000, trigger="manual"),
            _rec("response", text="b", input_tokens=50, context_window=1000),
            _rec("turn_end", reason="completed", iterations=2),
        ]
        result = pressure_series(records)
        self.assertEqual(1, len(result["cuts"]))
        self.assertEqual("manual", result["cuts"][0]["trigger"])
        self.assertEqual(1, result["cuts"][0]["at"])

    def test_a_log_predating_the_reason_reports_it_as_absent(self):
        # Not as automatic. The two are different statements and guessing between them
        # would put words in the writer's mouth.
        records = [
            _rec("session_start", schema=1), _rec("turn", n=1),
            _rec("response", text="a", input_tokens=100, context_window=1000),
            _rec("compaction", before=900, dropped=4, context_window=1000),
            _rec("turn_end", reason="completed", iterations=1),
        ]
        self.assertIsNone(pressure_series(records)["cuts"][0]["trigger"])

    def test_the_threshold_is_where_the_agent_actually_compacts(self):
        records = [
            _rec("session_start", schema=1), _rec("turn", n=1),
            _rec("response", text="a", input_tokens=100, context_window=1000),
            _rec("turn_end", reason="completed", iterations=1),
        ]
        result = pressure_series(records)
        self.assertEqual(1000, result["window"])
        self.assertEqual(850, result["threshold"])


if __name__ == "__main__":
    unittest.main()
