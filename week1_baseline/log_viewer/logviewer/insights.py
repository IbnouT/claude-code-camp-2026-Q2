"""Insights: what stands out in one session, and what it cost where.

The viewer's job is to ANSWER, not to display. A chronological render, however neat,
leaves the reader to work out what mattered. So this module decides what mattered, and
`logweb` only draws it.

Three rules shape everything here.

RELATIVE, NEVER ABSOLUTE. An outlier is unusual against THIS session's own median. A
fixed threshold would call every turn of an expensive session remarkable and nothing in
a cheap one, which is the opposite of useful. And a session too small to have a
distribution says so rather than promoting an ordinary turn.

DERIVE OR ABSTAIN. Every figure comes from the record. Where the record cannot support a
question, the answer is that it cannot, named precisely. A viewer that guessed would be
inventing data that looks exactly like data.

NEVER RE-SIMULATE. A counterfactual asks what the SAME recorded tokens would have cost
under different pricing. It never asks what a different model would have done, because
a different model would not have made the same calls and pretending otherwise is
fiction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Any

from .logview import Record, Turn, group_turns, prompt_occupancy, totals

#: Below this many samples a median is not a distribution, so nothing is called an
#: outlier. Three is the smallest set where one value can sit apart from two others.
MIN_SAMPLE = 3

#: How far above the median a value has to sit before it is worth a reader's
#: attention. Chosen so a call twice the typical one qualifies and ordinary variation
#: does not.
OUTLIER_FACTOR = 2.0

#: Rates in the catalog and in the log are per this many tokens. Stated once so no
#: arithmetic here quietly drops the divisor.
PER = 1_000_000

#: Order the findings appear in, which is the order someone opens a log in: what
#: broke, then what stopped, then what was expensive or slow.
SEVERITY = ("failure", "retry", "ceiling", "cost", "time", "context")


@dataclass
class Finding:
    """One thing worth a reader's attention, and where to look.

    ``turn`` and ``iteration`` are what make it a link rather than a remark. A finding
    that cannot say where it happened is a statistic, and this module does not deal in
    statistics.
    """

    kind: str
    headline: str
    turn: int | None = None
    iteration: int | None = None
    detail: str = ""

    @property
    def rank(self) -> int:
        return SEVERITY.index(self.kind) if self.kind in SEVERITY else len(SEVERITY)

    def __str__(self) -> str:
        where = f" turn={self.turn}" if self.turn is not None else ""
        return f"<Finding {self.kind}{where} headline={self.headline!r}>"

    __repr__ = __str__


@dataclass
class Distribution:
    """A set of measurements and what is unusual in it.

    ``enough`` is the honest part: with fewer than :data:`MIN_SAMPLE` values there is
    no distribution, and a reader is told that rather than shown a median of two.
    """

    values: list[float] = field(default_factory=list)

    @property
    def enough(self) -> bool:
        return len(self.values) >= MIN_SAMPLE

    @property
    def middle(self) -> float | None:
        return median(self.values) if self.values else None

    @property
    def largest(self) -> float | None:
        return max(self.values) if self.values else None

    def is_outlier(self, value: float) -> bool:
        if not self.enough or not self.middle:
            return False
        return value >= self.middle * OUTLIER_FACTOR

    def __str__(self) -> str:
        return (f"<Distribution n={len(self.values)} median={self.middle} "
                f"max={self.largest}>")

    __repr__ = __str__


def _activity(turn: Turn, limit: int = 5) -> str:
    """What the agent DID in one turn, from its tool calls.

    Names and arguments rather than counts, so the shape of a run is readable before
    any turn is opened. Truncated with a count, because a summary that ran to
    twenty-five entries would stop being one.
    """
    actions = []
    for record in turn.records:
        if record.phase != "tool_call":
            continue
        name = str(record.get("name") or "?").split("__")[-1]
        args = record.get("args") or {}
        if isinstance(args, dict) and args:
            first = next(iter(args.values()))
            actions.append(f"{name} {first}" if isinstance(first, (str, int, float))
                           else name)
        else:
            actions.append(name)
    if not actions:
        return ""
    shown = ", ".join(actions[:limit])
    rest = len(actions) - limit
    return f"{shown}, +{rest} more" if rest > 0 else shown


def call_durations(records: list[Record]) -> Distribution:
    """Every call's wall clock, from the responses that recorded one.

    A response with no duration is skipped rather than counted as zero. Logs written
    before the field existed would otherwise report every call as instant.
    """
    return Distribution([float(r.get("duration_ms"))
                         for r in records
                         if r.phase == "response" and r.get("duration_ms") is not None])


def turn_costs(turns: list[Turn]) -> Distribution:
    """Each turn's cost, from the turns that have one. Absent is not zero."""
    return Distribution([float(t.cost) for t in turns if t.cost is not None])


def slowest_call(records: list[Record]) -> tuple[Record, int | None] | None:
    """The slowest response and the turn it belongs to, or None if untimed."""
    best: tuple[Record, int | None] | None = None
    turn_number: int | None = None
    for record in records:
        if record.phase == "turn":
            turn_number = int(record.get("n") or 0) or turn_number
        if record.phase != "response" or record.get("duration_ms") is None:
            continue
        if best is None or float(record.get("duration_ms")) > float(
                best[0].get("duration_ms")):
            best = (record, turn_number)
    return best


def findings(records: list[Record]) -> list[Finding]:
    """Everything worth a reader's attention, most serious first.

    Ordered by kind rather than by size, because a reader opening a log wants to know
    what broke before what was expensive.
    """
    turns = group_turns(records)
    out: list[Finding] = []
    durations = call_durations(records)
    costs = turn_costs(turns)

    # Failures, per turn, so the count is actionable rather than a session total.
    for turn in turns:
        # Positions throughout, since a finding is only useful if its link resolves.
        number = turn.position
        failed = [r for r in turn.records
                  if r.phase == "tool_result" and not r.get("ok", True)]
        if failed:
            names = ", ".join(sorted({str(r.get("name") or "?") for r in failed}))
            out.append(Finding(
                kind="failure", turn=number,
                headline=f"turn {number}: {len(failed)} tool "
                         f"{'call' if len(failed) == 1 else 'calls'} failed",
                detail=names))
        retries = [r for r in turn.records if r.phase == "retry"]
        if retries:
            statuses = sorted({str(r.get("status") or r.get("error") or "?")
                               for r in retries})
            out.append(Finding(
                kind="retry", turn=number,
                headline=f"turn {number}: {len(retries)} transient "
                         f"{'failure' if len(retries) == 1 else 'failures'} retried",
                detail=", ".join(statuses)))
        if turn.tripped:
            limit = next((r for r in turn.records if r.phase == "limit_reached"), None)
            where = (f" at {limit.get('n')}/{limit.get('max')}" if limit else "")
            out.append(Finding(
                kind="ceiling", turn=number,
                headline=f"turn {number} tripped {turn.reason}{where}"))

    # Cost and time outliers, each against this session's own middle.
    if costs.enough:
        for turn in turns:
            if turn.cost is not None and costs.is_outlier(turn.cost):
                factor = turn.cost / costs.middle
                out.append(Finding(
                    kind="cost", turn=turn.position,
                    headline=f"turn {turn.position} cost ${turn.cost:.4f}, "
                             f"{factor:.1f}x the median turn"))
    slowest = slowest_call(records)
    if slowest and durations.enough:
        record, turn_number = slowest
        value = float(record.get("duration_ms"))
        if durations.is_outlier(value):
            out.append(Finding(
                kind="time", turn=turn_number,
                headline=f"slowest call {value / 1000:.1f}s against a "
                         f"{durations.middle / 1000:.1f}s median"))

    # Compaction is not a failure, and it is the loudest thing about a session's
    # window when it happens.
    for turn in turns:
        for record in turn.records:
            if record.phase != "compaction":
                continue
            did = []
            if record.get("dropped"):
                did.append(f"dropping {record.get('dropped')} messages")
            if record.get("compressed"):
                did.append(f"compressing {record.get('compressed')} tool results")
            if record.get("summarized"):
                did.append("keeping a journey note")
            still = " and was still over budget" if record.get("over_budget") else ""
            out.append(Finding(
                kind="context", turn=turn.position,
                headline=f"turn {turn.position} compacted, "
                         + (" and ".join(did) or "changing nothing") + still))

    return sorted(out, key=lambda f: (f.rank, f.turn or 0))


def why_nothing_stands_out(records: list[Record]) -> str | None:
    """Why a session produced no findings, when that needs saying.

    Silence has two causes and they are not the same. A clean run of many turns is
    good news. A run too small to have a distribution has simply not been measured,
    and telling a reader the difference is the point.
    """
    turns = group_turns(records)
    if not turns:
        return "no turns ran, so there is nothing to compare"
    costs = turn_costs(turns)
    durations = call_durations(records)
    if not costs.enough and not durations.enough:
        return (f"{len(turns)} "
                f"{'turn' if len(turns) == 1 else 'turns'} and "
                f"{len(durations.values)} timed "
                f"{'call' if len(durations.values) == 1 else 'calls'}, too few for a "
                f"median, so nothing is called unusual")
    return "no failures, no tripped ceilings, and nothing far from the median"


def turn_activity(records: list[Record]) -> list[dict[str, Any]]:
    """Per-turn shape: what it did, what it cost, how it ended.

    The turn strip reads from this, so the run is legible before a turn is opened.
    """
    rows = []
    for turn in group_turns(records):
        rows.append({
            "position": turn.position,
            "number": turn.number,
            "renumbered": turn.renumbered,
            "calls": len([r for r in turn.records if r.phase == "response"]),
            "iterations": turn.iterations,
            "reason": turn.reason,
            "tripped": turn.tripped,
            "cost": turn.cost,
            "tokens": turn.tokens,
            "duration_ms": turn.duration_ms,
            "amplification": turn.amplification,
            "activity": _activity(turn),
            "failures": len([r for r in turn.records
                             if r.phase == "tool_result" and not r.get("ok", True)]),
            "retries": len([r for r in turn.records if r.phase == "retry"]),
        })
    return rows


def window_pressure(records: list[Record]) -> dict[str, Any]:
    """How close the session came to the model's context limit.

    ``window`` comes from the record rather than from a table of model limits, which
    this program deliberately does not own.
    """
    prompts = [prompt_occupancy(r) for r in records if r.phase == "response"]
    windows = [int(r.get("context_window")) for r in records
               if r.get("context_window") is not None]
    peak = max(prompts) if prompts else 0
    window = max(windows) if windows else None
    compactions = [r for r in records if r.phase == "compaction"]
    return {
        "peak_prompt": peak,
        "window": window,
        "peak_fraction": (peak / window) if window else None,
        "compactions": len(compactions),
        "still_over_budget": sum(1 for r in compactions if r.get("over_budget")),
    }


def attribution(records: list[Record]) -> dict[str, Any]:
    """Where the money went, and how much of it was repetition.

    Amplification is READ, never computed. Its denominator is the count of distinct
    things sent, which the agent tracks and the message stream does not record, so a
    viewer computing its own would be inventing a number. Absent, it says so.
    """
    turns = group_turns(records)
    figures = totals(records)
    priced = [t for t in turns if t.cost is not None]
    largest = max(priced, key=lambda t: t.cost) if priced else None
    amps = [t.amplification for t in turns if t.amplification is not None]
    classes = {"fresh_input": 0, "cache_read": 0, "cache_write": 0, "output": 0}
    seen_classes = False
    for turn in turns:
        if not turn.usage:
            continue
        seen_classes = True
        for key in classes:
            classes[key] += int(turn.usage.get(key) or 0)
    # The session total prefers the per-CALL figures, the finest thing the writer
    # recorded. Where a log carries cost only on its turns, the turn sum stands in
    # rather than reporting unavailable beside turns that each show a price, which
    # would have the page disagreeing with itself. Which source was used is reported,
    # because the two are not interchangeable and a reader may need to know.
    total, source = figures["cost"], "calls"
    if total is None and priced:
        total, source = round(sum(t.cost for t in priced), 8), "turns"
    return {
        "total": total,
        "total_from": source if total is not None else None,
        "partial": figures["cost_partial"],
        "largest_turn": largest.number if largest else None,
        "largest_turn_cost": largest.cost if largest else None,
        "amplification": max(amps) if amps else None,
        "amplification_available": bool(amps),
        # Amplification's denominator. A ratio without it is a conclusion with its
        # evidence withheld.
        "unique_tokens": max((t.unique_tokens for t in turns
                              if t.unique_tokens is not None), default=None),
        "classes": classes if seen_classes else None,
        "unpriced_turns": len(turns) - len(priced),
    }


def repetition(records: list[Record]) -> dict[str, Any]:
    """How much of the volume was history re-sent, from the classes alone.

    This is the counterfactual's honest half. The share of input served from cache is
    a fact in the record. What it SAVED is not, because that needs the per-class rates
    and this program does not own a price table, so :func:`cache_saving` asks the
    record for them and abstains when they are absent.
    """
    figures = attribution(records)
    classes = figures["classes"]
    if not classes:
        return {"available": False,
                "why": "this session recorded no per-class usage, so cache reads "
                       "cannot be separated from fresh input"}
    prompt = classes["fresh_input"] + classes["cache_read"] + classes["cache_write"]
    if not prompt:
        return {"available": False, "why": "no input tokens were recorded"}
    return {
        "available": True,
        "prompt_tokens": prompt,
        "cache_read": classes["cache_read"],
        "cache_write": classes["cache_write"],
        "fresh_input": classes["fresh_input"],
        "cached_share": classes["cache_read"] / prompt,
    }


def cache_saving(records: list[Record]) -> dict[str, Any]:
    """What caching saved on this session, or why the record cannot say.

    Needs the per-class RATES. They are a fact about the model, not about the run, so
    a reader can only have them if the writer recorded them. Where it did not, this
    abstains and names what is missing rather than reaching for a price table, which
    would put a second cost calculation in the one program that must never disagree
    with the bill.
    """
    rates = None
    for record in records:
        if record.phase == "session_start" and record.get("rates"):
            rates = record.get("rates")
            break
    share = repetition(records)
    if not share.get("available"):
        return {"available": False, "why": share["why"]}
    if not isinstance(rates, dict) or not rates:
        return {"available": False,
                "why": "this session did not record its per-class rates, and this "
                       "program owns no price table: a second cost calculation is "
                       "exactly what a reader must not have"}
    fresh_rate = rates.get("input")
    read_rate = rates.get("cache_read")
    if fresh_rate is None or read_rate is None:
        missing = [n for n, v in (("input", fresh_rate), ("cache_read", read_rate))
                   if v is None]
        return {"available": False,
                "why": f"the recorded rates are missing {', '.join(missing)}"}
    # The same recorded tokens, priced as if none of them had been cached. No
    # re-simulation: the calls are the calls that happened.
    #
    # Rates are PER MILLION tokens, which is how the catalog states them and how the
    # writer priced the bill. Multiplying tokens by a per-million rate without the
    # divisor overstates by a factor of a million, and it looks like a plausible
    # number rather than an error, so the unit is named here and asserted in the test.
    reads = share["cache_read"]
    as_if = reads * float(fresh_rate) / PER
    paid = reads * float(read_rate) / PER
    return {
        "available": True,
        "cached_tokens": reads,
        "saved": as_if - paid,
        "as_if_uncached": as_if,
        "actually_paid": paid,
    }


def diff(left: list[Record], right: list[Record]) -> list[dict[str, Any]]:
    """Two sessions side by side, field by field.

    A field one side lacks is reported as missing rather than as zero, because a
    session that never recorded amplification did not have an amplification of none.
    """
    def snapshot(records: list[Record]) -> dict[str, Any]:
        figures = totals(records)
        turns = group_turns(records)
        start = next((r for r in records if r.phase == "session_start"), None)
        amps = [t.amplification for t in turns if t.amplification is not None]
        window = window_pressure(records)
        return {
            "model": start.get("model") if start else None,
            "turns": figures["turns"],
            "iterations": figures["iterations"],
            "calls": figures["calls"],
            "cost": figures["cost"],
            "peak prompt": window["peak_prompt"] or None,
            "failures": figures["failures"],
            "compactions": figures["compactions"],
            "ended": figures["end_reason"],
            "amplification": max(amps) if amps else None,
        }

    a, b = snapshot(left), snapshot(right)
    rows = []
    for key in a:
        one, two = a[key], b[key]
        if one is None or two is None:
            change = "not recorded"
        elif isinstance(one, str) or isinstance(two, str):
            change = "same" if one == two else "different"
        elif one == two:
            change = "same"
        elif one:
            change = f"{(two - one) / one * 100:+.0f}%"
        else:
            change = f"{two - one:+g}"
        rows.append({"field": key, "left": one, "right": two, "change": change})
    return rows

def cost_cause(records: list[Record]) -> list[dict[str, Any]]:
    """Why a turn cost what it did, linked to the effect rather than stated beside it.

    A turn's cost rises for two reasons a reader can act on: it made more calls, or each
    call carried more history. Both are in the record, so the attribution is a fact.

    A turn with no such cause says nothing. Inventing an explanation for ordinary
    variation is worse than leaving it unexplained, because a plausible cause stops the
    reader looking for the real one.
    """
    turns = group_turns(records)
    rows = []
    previous = None
    for turn in turns:
        prompts = [prompt_occupancy(r) for r in turn.records
                   if r.phase == "response"]
        calls = len(prompts)
        carried = max(prompts) if prompts else 0
        row = {"turn": turn.position, "calls": calls, "peak_prompt": carried,
               "cost": turn.cost, "cause": None}
        if previous and turn.cost is not None and previous["cost"]:
            ratio = turn.cost / previous["cost"]
            if ratio >= 1.5:
                reasons = []
                if previous["calls"] and calls > previous["calls"]:
                    reasons.append(f"{calls} calls against {previous['calls']}")
                if previous["peak_prompt"] and carried > previous["peak_prompt"] * 1.1:
                    reasons.append(f"a prompt reaching {carried:,} against "
                                   f"{previous['peak_prompt']:,}")
                if reasons:
                    row["cause"] = (f"{ratio:.1f}x turn {previous['turn']}, from "
                                    + " and ".join(reasons))
        rows.append(row)
        previous = row
    return rows


#: A room heading in MUD output: the first line of a look or a successful move, which
#: the game prints as a title before the description. Used to count distinct places
#: rather than to identify them: two rooms can share a name, which is why the agent's
#: own parser correlates against the world files and this one does not pretend to.
def rooms_seen(records: list[Record],
               resolved: int | None = None) -> dict[str, Any]:
    """Progress per token, and an honest refusal when there is no progress to measure.

    Counts identified ROOMS when the world files are available, because they can tell
    two rooms with one name apart, and falls back to distinct HEADINGS when they are not.
    Which one it did is reported, since the two are not the same measure: this world has
    241 titles shared by more than one room.
    """
    headings: list[str] = []
    for record in records:
        if record.phase != "tool_result" or not record.get("ok", True):
            continue
        text = str(record.get("result") or "")
        first = next((line.strip() for line in text.splitlines() if line.strip()), "")
        # A heading is short, titled, and not a sentence. Anything else is prose or a
        # refusal from the game, and counting those would inflate the measure.
        if first and len(first) < 60 and not first.endswith((".", "!", "?")):
            headings.append(first)
    distinct = list(dict.fromkeys(headings))
    figures = totals(records)
    if resolved:
        # Identified rooms beat distinct headings wherever they are available.
        return _per_room(resolved, len(headings), figures, "rooms")
    if not distinct:
        return {"available": False,
                "why": "no tool result in this session looks like a room heading, so "
                       "there is no progress measure here rather than a zero"}
    return _per_room(len(distinct), len(headings), figures, "headings")


def _per_room(count: int, visits: int, figures: dict[str, Any],
              basis: str) -> dict[str, Any]:
    """Work and money per place reached, and which kind of place was counted."""
    cost = figures["cost"]
    volume = figures["input_tokens"] + figures["output_tokens"]
    return {
        "available": True,
        "basis": basis,
        "headings": count,
        "visits": visits,
        "tokens_each": round(volume / count) if volume and count else None,
        "cost_each": (cost / count) if cost and count else None,
    }


# -- the journey, in the four words the brief uses ---------------------------

#: A room entered this many times without the agent's state changing reads as going in
#: circles. Three, because twice can be a route through and three times is a pattern.
CIRCLING = 3

#: Consecutive identical successful actions that stop being progress and start being
#: filler. Four, so a corridor of three moves in one direction is not flagged.
GRINDING = 4

#: Iterations inside one turn with no new room reached. Eight is generous on purpose: a
#: turn can legitimately spend calls reading and deciding.
STUCK = 8


@dataclass
class JourneyFinding:
    """One thing the PLAYER experienced, rather than one thing the run did.

    The brief names four: confused, blocked, bored, overpowered. This computes them from
    the log rather than leaving a reader to notice them, which is the difference between
    a viewer and a report.
    """

    word: str
    headline: str
    evidence: str = ""
    turn: int | None = None

    def __str__(self) -> str:
        return f"<JourneyFinding {self.word} headline={self.headline!r}>"

    __repr__ = __str__


def _mud_actions(records: list[Record]) -> list[dict[str, Any]]:
    """Every MUD action with what the world said back, in order.

    Derived from the tool calls, so a session whose tools are something else yields
    nothing and every journey finding is honestly absent rather than invented.
    """
    from .html import strip_ansi

    turn = 0
    results = {str(r.get("tool_use_id") or r.get("name")): r
               for r in records if r.phase == "tool_result"}
    out = []
    for record in records:
        if record.phase == "turn":
            turn = int(record.get("n") or turn)
        if record.phase != "tool_call":
            continue
        result = results.get(str(record.get("id") or record.get("name")))
        text = strip_ansi(str(result.get("result") or "")) if result else ""
        first = next((line.strip() for line in text.splitlines() if line.strip()), "")
        # A room heading is short, titled, and not a sentence. Counting a message as a
        # room made a level gate refused thirteen times read as going in circles, which
        # is the wrong finding from the right data.
        room = first if (first and len(first) < 60
                         and not first.endswith((".", "!", "?"))) else ""
        args = record.get("args") or {}
        out.append({
            "turn": turn,
            "tool": str(record.get("name") or "?").split("__")[-1],
            "args": args if isinstance(args, dict) else {},
            "room": room,
            "said": first,
            "text": text,
            "ok": bool(result and result.get("ok", True)),
        })
    return out


def journey_findings(records: list[Record]) -> list[JourneyFinding]:
    """The four words, computed. Each carries the evidence that produced it.

    Nothing here is a guess dressed as a diagnosis: every finding names the count or the
    room that triggered it, so a reader can disagree with the threshold rather than
    having to trust the label.
    """
    actions = _mud_actions(records)
    if not actions:
        return []
    out: list[JourneyFinding] = []

    # CONFUSED: the same room over and over. Going in circles is the clearest signal a
    # player has lost the thread, and it is invisible in a chronological read.
    visits: dict[str, list[int]] = {}
    for action in actions:
        if action["ok"] and action["room"]:
            visits.setdefault(action["room"], []).append(action["turn"])
    for room, turns in sorted(visits.items(), key=lambda kv: -len(kv[1])):
        if len(turns) < CIRCLING:
            continue
        out.append(JourneyFinding(
            word="confused", turn=turns[0],
            headline=f"entered {room} {len(turns)} times",
            evidence=f"on turns {', '.join(str(t) for t in sorted(set(turns)))}"))
        break

    # BLOCKED: the world refusing the same action. A wall walked into repeatedly is a
    # player who has not understood why.
    refused: dict[str, int] = {}
    for action in actions:
        if action["ok"]:
            continue
        key = f"{action['tool']} {' '.join(str(v) for v in action['args'].values())}"
        refused[key] = refused.get(key, 0) + 1
    for what, count in sorted(refused.items(), key=lambda kv: -kv[1]):
        if count < 2:
            continue
        out.append(JourneyFinding(
            word="blocked", headline=f"{what.strip()} refused {count} times",
            evidence="the world said no and the agent asked again"))
        break

    # BORED: long runs of the same successful action, which is motion without progress.
    run = 1
    for previous, action in zip(actions, actions[1:]):
        same = (action["tool"] == previous["tool"]
                and action["args"] == previous["args"] and action["ok"])
        run = run + 1 if same else 1
        if run >= GRINDING:
            what = f"{action['tool']} " + " ".join(
                str(v) for v in action["args"].values())
            out.append(JourneyFinding(
                word="bored", turn=action["turn"],
                headline=f"{run} identical {what.strip()} in a row",
                evidence="the same action repeated with the same arguments"))
            break

    # STUCK: a turn burning iterations without reaching anywhere new. Named separately
    # from confused because the cause differs: this is a turn that never got going.
    by_turn: dict[int, list[dict[str, Any]]] = {}
    for action in actions:
        by_turn.setdefault(action["turn"], []).append(action)
    for turn, group in sorted(by_turn.items()):
        rooms = {a["room"] for a in group if a["ok"] and a["room"]}
        if len(group) >= STUCK and len(rooms) <= 1:
            out.append(JourneyFinding(
                word="stuck", turn=turn,
                headline=f"turn {turn} spent {len(group)} actions and reached "
                         f"{len(rooms)} new place" + ("" if len(rooms) == 1 else "s"),
                evidence="actions without movement"))
            break

    # OVERPOWERED: the game saying outright that the agent is out of its depth. The
    # clearest of the four, because the world states it rather than leaving it to be
    # inferred, and it is a wall no amount of trying gets through.
    gates = [a for a in actions if "above your recommended level" in a["text"].lower()]
    if gates:
        out.append(JourneyFinding(
            word="overpowered", turn=gates[0]["turn"],
            headline=f"the world refused a zone as above the agent's level "
                     f"{len(gates)} times",
            evidence="a level gate, which trying again cannot pass"))

    # And a resource run to nothing, which is the same experience by a slower route: a
    # player immobilised by hunger or exhaustion has stopped being able to play. This is
    # the one a human spotted in a header rather than in any view.
    for action in actions:
        lowered = action["text"].lower()
        for phrase, word in (("too exhausted", "exhausted, out of movement"),
                             ("you are hungry", "hungry"),
                             ("you are thirsty", "thirsty"),
                             ("you die", "death"),
                             ("you are dead", "death")):
            if phrase in lowered:
                out.append(JourneyFinding(
                    word="drained", turn=action["turn"],
                    headline=f"the game reported {word}",
                    evidence=f"during {action['tool']}: "
                             f"{action['text'].strip().splitlines()[0][:70]}"))
                break
        else:
            continue
        break
    return out


def why_no_journey(records: list[Record]) -> str:
    """Why a session produced no journey findings, when that needs saying."""
    if not _mud_actions(records):
        return ("this session's tools are not MUD tools, so there is no journey to "
                "read here")
    return ("no circling, no repeated refusal, no long identical run and no resource "
            "run to nothing")


# -- window pressure over time ---------------------------------------------

def pressure_series(records: list[Record]) -> dict[str, Any]:
    """Prompt size per call against the window, with the compactions marked.

    The one view that shows a compaction WORKING. Both compaction records in this
    project's whole corpus sat inside turns no page could reach until this pass, so this
    is the first drawing of a thing that has been happening unseen.
    """
    window = None
    points: list[dict[str, Any]] = []
    cuts: list[dict[str, Any]] = []
    turn = 0
    index = 0
    for record in records:
        if record.phase == "turn":
            turn = int(record.get("n") or turn)
        if record.get("context_window") is not None:
            window = int(record.get("context_window"))
        if record.phase == "compaction":
            cuts.append({
                "at": index, "turn": turn,
                "before": record.get("before"),
                "dropped": record.get("dropped") or 0,
                "compressed": record.get("compressed") or 0,
                "over_budget": bool(record.get("over_budget")),
                # Why it happened. Absent on a log that predates the field, which is a
                # different statement from a compaction with no reason.
                "trigger": record.get("trigger"),
            })
        if record.phase != "response":
            continue
        index += 1
        points.append({
            "at": index, "turn": turn,
            "prompt": prompt_occupancy(record),
            "output": int(record.get("output_tokens") or 0),
        })
    if not points:
        return {"available": False,
                "why": "no model call in this session recorded its usage, so there is "
                       "no pressure to draw"}
    peak = max(p["prompt"] for p in points)
    return {
        "available": True, "points": points, "cuts": cuts, "window": window,
        "peak": peak,
        "peak_fraction": (peak / window) if window else None,
        # The threshold the agent compacts at, so the line has something to be near.
        "threshold": int(window * 0.85) if window else None,
    }
