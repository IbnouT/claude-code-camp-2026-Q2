"""Publish a sample of this logger's format, for readers of it to test against.

The log viewer is a separate program that reads these files and imports nothing from
here. It still needs a log carrying every phase and every field to test against, and
hand-authoring one would test a guess about the format rather than the format.

So the WRITER publishes the sample. This runs a real turn through the real chain over
a scripted transport, adds the phases one turn cannot produce, and writes the result
wherever it is told. That direction matters: a reader asking the writer for a sample is
a file dependency, while a reader importing the writer to build one is not.

Not a test, and named so unittest discovery skips it. Run it deliberately when the
vocabulary changes, and the reader's own tests then fail until they account for what
is new, which is the point.

    uv run python -m tests.make_fixture ../../log_viewer/tests/fixtures/every_phase.jsonl
"""

from __future__ import annotations

import sys
from pathlib import Path

from boukensha.message import Message

from .helper import (
    StubTransport, add_ping_tool, build_agent, end_turn, ok, tool_use,
)

#: Where the log viewer keeps it, relative to this step directory.
DEFAULT_TARGET = Path("../../log_viewer/tests/fixtures/every_phase.jsonl")


def write(target: str | Path = DEFAULT_TARGET) -> Path:
    """Write one session carrying every phase, and return where it landed."""
    target = Path(target).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()

    # A ceiling low enough to trip, so limit_reached and a wind-down both appear.
    # The second reply reports CACHE READS, because a fixture whose every token is
    # fresh cannot exercise a reader's caching arithmetic at all: the saving would be
    # zero for the right reason and the code path would go unproven.
    cached_reply = end_turn("I reached my token limit for this turn.",
                            itok=120, otok=30)
    cached_reply["usage"].update({"cache_read_input_tokens": 1180,
                                 "cache_creation_input_tokens": 0})
    agent, assembled = build_agent(
        StubTransport(ok(tool_use("ping", itok=1200, otok=40)),
                      ok(cached_reply)),
        "log_fixture", setup=add_ping_tool,
        max_turn_tokens=1000, max_iterations=25)
    logger = assembled.logger

    # The instruction a real turn starts from, so the logged prompt payload carries
    # a message and a reader of it has something to diff.
    assembled.context.add(Message.user("find the menu at the bakery"))
    # The REPL opens the turn, and the phases one stubbed turn cannot produce go
    # here so they sit inside it, before its turn_end.
    logger.turn(n=1)
    logger.plan(text="I will look around first, then follow the exits north.")
    logger.reasoning(text="The bakery is usually near the market square.")
    logger.compaction(before=178_000, dropped=4, context_window=200_000,
                      compressed=2, summarized=True, over_budget=False)
    logger.retry(attempt=1, wait=0.5, status=529)
    # A failed result whose call is absent, which is the unpaired case a reader
    # must not drop: half a pair is usually the thing being investigated.
    logger.tool_result(name="move", result="You cannot go that way.", ok=False,
                       error="blocked exit", tool_use_id="toolu_blocked")
    logger._debug = True
    logger.raw(data={"provider_body": "verbatim, debug only"})
    logger._debug = False
    agent.run()
    logger.close()

    target.write_text(Path(logger.path).read_text(encoding="utf-8"),
                      encoding="utf-8")
    return target


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TARGET
    written = write(target)
    lines = [l for l in written.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"{written}: {len(lines)} events")


if __name__ == "__main__":
    main()
