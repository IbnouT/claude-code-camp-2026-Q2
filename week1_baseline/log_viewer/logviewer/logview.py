"""Logview: read a session log into records, and derive what a reader asks of it.

The logger is the only writer and the JSONL file is the interface, so this is a
READER over a contract rather than a second implementation. It imports no agent, no
backend and no REPL, which is why a session written by any earlier step can be read
by this one.

Two rules shape everything here:

- Render what the writer recorded, derive nothing it already computed. Cost is
  calculated once at the call site where the model, the usage and the rates are all
  in hand, and logged as a fact. A reader that recomputed it would eventually
  disagree with the bill, which is worse than not showing it.
- Be tolerant at the edges. A live session is being appended to while it is read, so
  the final line is often half written. That is "in progress", not corruption, and
  an unknown phase from a newer step renders rather than raising.

This module holds no presentation. It produces records and figures that a terminal
renderer, a web page, or a test can each consume, so the medium is a separate
decision from the reading.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

#: Phases the writer emits, in the order a turn produces them. Used for grouping
#: and filtering, never to reject: a session from a newer step may carry a phase
#: this list has not heard of, and it still has to be readable.
KNOWN_PHASES = (
    "session_start", "turn", "iteration", "prompt", "response",
    "tool_call", "tool_result", "reasoning", "plan", "compaction",
    "retry", "limit_reached", "turn_end", "raw", "log_error",
)

#: Phases that are a failure or a warning rather than an ordinary leg. A reader
#: opens a log because something went wrong, so these can never render quietly.
TROUBLE_PHASES = frozenset({"retry", "limit_reached", "log_error"})


@dataclass(frozen=True)
class Record:
    """One logged event: its phase, its fields, and where it came from.

    ``line`` is kept so a malformed record can be reported by position, which is
    the only useful thing to say about a line that will not parse.
    """

    phase: str
    data: dict[str, Any]
    line: int
    malformed: bool = False

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    @property
    def known(self) -> bool:
        return self.phase in KNOWN_PHASES

    @property
    def trouble(self) -> bool:
        """Whether this record is a failure a reader must not miss."""
        if self.phase in TROUBLE_PHASES:
            return True
        # A tool result carries its own success flag.
        return self.phase == "tool_result" and not self.data.get("ok", True)

    def __str__(self) -> str:
        if self.malformed:
            return f"<Record malformed line={self.line}>"
        return f"<Record {self.phase} line={self.line} fields={len(self.data)}>"

    __repr__ = __str__


@dataclass
class ReadResult:
    """What one read of a session file produced.

    ``offset`` is where reading stopped, so following a live session continues from
    there instead of re-reading. ``incomplete`` means the file ended mid-line, which
    is the normal state of a session still being written.
    """

    records: list[Record] = field(default_factory=list)
    offset: int = 0
    incomplete: bool = False
    malformed: int = 0

    def __str__(self) -> str:
        return (f"<ReadResult records={len(self.records)} offset={self.offset} "
                f"incomplete={self.incomplete} malformed={self.malformed}>")

    __repr__ = __str__


def parse_line(text: str, number: int) -> Record | None:
    """One line to a Record. Blank lines are nothing, bad lines are reported."""
    stripped = text.strip()
    if not stripped:
        return None
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return Record(phase="malformed", data={"raw": stripped[:200]},
                      line=number, malformed=True)
    if not isinstance(data, dict):
        return Record(phase="malformed", data={"raw": stripped[:200]},
                      line=number, malformed=True)
    return Record(phase=str(data.get("phase") or "unknown"), data=data,
                  line=number)


def read(path: str | Path, start: int = 0) -> ReadResult:
    """Read a session file from ``start``, tolerating a half-written final line.

    A complete line ends with a newline. If the file's tail has no newline yet, the
    writer is mid-append: that fragment is left unread and ``offset`` stops before
    it, so the next read picks it up whole rather than parsing half an object or
    reporting it as damage.
    """
    path = Path(path)
    result = ReadResult(offset=start)
    if not path.exists():
        return result
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        handle.seek(start)
        text = handle.read()
    if not text:
        return result

    consumed = text
    if not text.endswith("\n"):
        cut = text.rfind("\n")
        if cut == -1:
            # Not even one complete line yet.
            result.incomplete = True
            return result
        consumed = text[:cut + 1]
        result.incomplete = True

    number = _line_number_at(path, start)
    for raw in consumed.splitlines():
        number += 1
        record = parse_line(raw, number)
        if record is None:
            continue
        if record.malformed:
            result.malformed += 1
        result.records.append(record)
    result.offset = start + len(consumed.encode("utf-8"))
    return result


def _line_number_at(path: Path, offset: int) -> int:
    """How many lines precede ``offset``, so reported numbers match the file."""
    if offset <= 0:
        return 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return handle.read(offset).count("\n")


def follow(path: str | Path, start: int = 0) -> Iterator[Record]:
    """Yield records from one read. Call again with the returned offset to continue.

    Deliberately not a loop with a sleep in it: a caller owns its own timing, and a
    generator that blocked would be unusable from a UI thread or a test.
    """
    yield from read(path, start).records


#: The provider keys each input class appears under. A prompt total that read only
#: ``input_tokens`` would repeat the exact defect the agent had to fix: on some
#: providers that figure EXCLUDES the cached portion.
_FRESH_KEYS = ("input_tokens", "prompt_tokens", "promptTokenCount",
               "prompt_eval_count")
_CACHE_READ_KEYS = ("cache_read_input_tokens", "cached_tokens",
                    "cachedContentTokenCount", "cache_read_tokens")
_CACHE_WRITE_KEYS = ("cache_creation_input_tokens", "cache_write_tokens")

#: Providers that report a prompt total INCLUDING its cached portion. Adding the
#: classes on those would double count, which is the mirror-image error.
_INCLUSIVE_PROMPT_KEYS = frozenset({"prompt_tokens", "promptTokenCount"})


def _first(usage: dict[str, Any], keys: tuple[str, ...]) -> tuple[int, str | None]:
    for key in keys:
        if usage.get(key) is not None:
            return int(usage[key] or 0), key
    return 0, None


def prompt_occupancy(record: Record) -> int:
    """How much of the window one call's prompt occupied.

    Fresh input plus cache reads plus cache writes, because a cached token is still in
    the window: caching changes a token's price, never its presence. Where the
    provider's own prompt total already includes the cached portion, the classes are
    not added on top.

    Falls back to the flat ``input_tokens`` the writer records beside the nested usage,
    so a log from before per-class usage existed still reports a prompt size.
    """
    usage = record.get("usage")
    if isinstance(usage, dict) and usage:
        fresh, key = _first(usage, _FRESH_KEYS)
        if key in _INCLUSIVE_PROMPT_KEYS:
            return fresh
        reads, _ = _first(usage, _CACHE_READ_KEYS)
        writes, _ = _first(usage, _CACHE_WRITE_KEYS)
        return fresh + reads + writes
    return int(record.get("input_tokens") or 0)


# -- what a reader asks of a session ---------------------------------------

@dataclass
class Turn:
    """One turn's legs, grouped, with how it ended and what it cost.

    Every figure here is READ from the turn's own ``turn_end`` record rather than
    re-summed from its responses. The writer already added them up, and a reader
    that added them up again would eventually disagree with the writer over
    rounding or over a call it grouped differently.

    ``amplification`` is the one figure no reader could produce. Its denominator
    is the count of distinct things sent, which the agent tracks and the message
    stream does not record, so it is read or it is absent.
    """

    #: Where this turn sits in the file, counting from one. THIS is its identity.
    #: The recorded ``n`` is not: `/retry` and `/undo` deliberately reuse a turn
    #: number when a turn is redone, so a log can legitimately carry four turns all
    #: labelled 3, and a reader that addressed turns by ``n`` reached the first and
    #: silently hid the rest. On the sessions here that hid three turns and both
    #: compaction records in the entire corpus.
    position: int = 0
    #: The number the writer recorded, kept as DATA rather than used as a key.
    number: int = 0
    #: Which attempt at that number this is, when the writer said so. Present means
    #: the reuse was DELIBERATE, a turn redone with `/retry` or `/undo`. Absent on a
    #: repeated number means an older log that did not record the distinction, and the
    #: two deserve different words rather than one guess.
    attempt: int | None = None
    records: list[Record] = field(default_factory=list)
    iterations: int = 0
    reason: str | None = None
    tokens: int = 0
    cost: float | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    usage: dict[str, int] | None = None
    unique_tokens: int | None = None
    amplification: float | None = None
    duration_ms: float | None = None

    @property
    def tripped(self) -> bool:
        """Whether a ceiling ended this turn rather than the model finishing."""
        return bool(self.reason) and self.reason != "completed"

    @property
    def renumbered(self) -> bool:
        """Whether the recorded number disagrees with where the turn actually sits.

        True on a redone turn, and worth saying rather than hiding: a reader looking
        at turn 4 of 6 needs to know the log calls it 3.
        """
        return bool(self.number) and self.number != self.position

    def render_cost(self) -> str:
        """Money, or an honest absence. A zero would read as free."""
        return "unavailable" if self.cost is None else f"${self.cost:.4f}"

    def __str__(self) -> str:
        label = (f"{self.position} (logged as {self.number})" if self.renumbered
                 else str(self.position))
        return (f"<Turn {label} legs={len(self.records)} "
                f"iterations={self.iterations} reason={self.reason}>")

    __repr__ = __str__


def group_turns(records: list[Record]) -> list[Turn]:
    """Split a session's records into turns, in the order they happened.

    Records before the first ``turn`` (the session snapshot) belong to no turn and
    are not lost: a caller reads them from the records list directly.

    Turns come back in FILE ORDER with a position each, and the recorded number beside
    it. A number can repeat, because a redone turn keeps its number, so position is the
    only thing that identifies a turn in a file.
    """
    turns: list[Turn] = []
    current: Turn | None = None
    for record in records:
        if record.phase == "turn":
            current = Turn(position=len(turns) + 1,
                           number=int(record.get("n") or len(turns) + 1),
                           attempt=record.get("attempt"))
            turns.append(current)
            continue
        if current is None:
            continue
        current.records.append(record)
        if record.phase == "iteration":
            current.iterations = int(record.get("n") or current.iterations)
        elif record.phase == "turn_end":
            current.reason = record.get("reason")
            current.tokens = int(record.get("tokens") or 0)
            current.input_tokens = int(record.get("input_tokens") or 0)
            current.output_tokens = int(record.get("output_tokens") or 0)
            # None stays None. A turn on an unpriced model has no cost, which is
            # a different statement from a turn that cost nothing.
            current.cost = record.get("cost_usd")
            current.usage = record.get("usage")
            current.unique_tokens = record.get("unique_tokens")
            current.amplification = record.get("amplification")
            current.duration_ms = record.get("duration_ms")
            if current.iterations == 0:
                current.iterations = int(record.get("iterations") or 0)
    return turns


def pair_tools(records: list[Record]) -> list[tuple[Record, Record | None]]:
    """Each tool call with its result, matched by id.

    An unpaired call is returned with ``None`` rather than dropped: a call whose
    result never arrived is usually the very thing being investigated.
    """
    results: dict[str, Record] = {}
    for record in records:
        if record.phase == "tool_result":
            key = str(record.get("tool_use_id") or record.get("name"))
            results.setdefault(key, record)
    out = []
    for record in records:
        if record.phase != "tool_call":
            continue
        key = str(record.get("id") or record.get("name"))
        out.append((record, results.get(key)))
    return out


def totals(records: list[Record]) -> dict[str, Any]:
    """The figures a reader wants about a whole session.

    Every number is read from what the writer logged. Cost is summed from the
    per-call values it recorded, never recalculated from tokens and rates, so this
    cannot drift from the bill. ``cost`` is None when no call reported one, which
    means unavailable rather than free.
    """
    responses = [r for r in records if r.phase == "response"]
    costs = [r.get("cost_usd") for r in responses if r.get("cost_usd") is not None]
    # Prompt sizes count every input class, because a cached token still occupies the
    # window. Reading the flat ``input_tokens`` alone understates a cached prompt
    # eightfold on a real session, which is the same defect the agent had to fix and
    # which a reader can reintroduce for free.
    inputs = [prompt_occupancy(r) for r in responses]
    outputs = [int(r.get("output_tokens") or 0) for r in responses]
    turns = group_turns(records)
    tool_calls = [r for r in records if r.phase == "tool_call"]
    failures = [r for r in records if r.trouble]

    return {
        "calls": len(responses),
        "turns": len(turns),
        "iterations": sum(t.iterations for t in turns),
        "input_tokens": sum(inputs),
        "output_tokens": sum(outputs),
        # The largest single prompt, which is the window-pressure question.
        "peak_input_tokens": max(inputs) if inputs else 0,
        "cost": round(sum(costs), 8) if costs else None,
        "cost_partial": bool(costs) and len(costs) < len(responses),
        "tool_calls": len(tool_calls),
        "failures": len(failures),
        "compactions": len([r for r in records if r.phase == "compaction"]),
        "end_reason": turns[-1].reason if turns else None,
        # Positions, not recorded numbers, so a caller can address what it names.
        "tripped": [t.position for t in turns if t.tripped],
        "largest_turn": max(turns, key=lambda t: t.tokens).position if turns else None,
        "busiest_turn": (max(turns, key=lambda t: t.iterations).position
                         if turns else None),
        "renumbered": [t.position for t in turns if t.renumbered],
    }


def cost_breakdown(records: list[Record]) -> list[dict[str, Any]]:
    """Cost grouped by task, provider and model, so a bill can be attributed.

    Rows carry ``cost_known`` false when a model in the group reported no cost, so a
    partial total is never presented as complete.
    """
    rows: dict[tuple, dict[str, Any]] = {}
    for record in records:
        if record.phase != "response":
            continue
        key = (record.get("task") or "unknown",
               record.get("provider") or "unknown",
               record.get("model") or "unknown")
        row = rows.setdefault(key, {
            "task": key[0], "provider": key[1], "model": key[2],
            "calls": 0, "input_tokens": 0, "output_tokens": 0,
            "cost": 0.0, "cost_known": True,
        })
        row["calls"] += 1
        row["input_tokens"] += int(record.get("input_tokens") or 0)
        row["output_tokens"] += int(record.get("output_tokens") or 0)
        amount = record.get("cost_usd")
        if amount is None:
            row["cost_known"] = False
        else:
            row["cost"] += float(amount)
    for row in rows.values():
        row["cost"] = round(row["cost"], 8)
    return sorted(rows.values(), key=lambda r: (-r["calls"], r["model"]))
