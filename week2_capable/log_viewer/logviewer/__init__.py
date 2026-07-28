"""Logviewer: read a boukensha session log and make it answerable.

An INDEPENDENT program, not a part of the agent. Its only input is the JSONL file
the agent's logger writes, and it imports nothing from the agent to read it. That is
deliberate: a reader meant to outlive its writer cannot be welded to it, and a log
written by any version has to stay readable by this one.

The whole public surface is here so a caller never reaches into a submodule.
"""

from .insights import (
    MIN_SAMPLE, OUTLIER_FACTOR, PER, Distribution, Finding, attribution,
    CIRCLING, GRINDING, STUCK, JourneyFinding, cache_saving, call_durations, cost_cause, diff, findings,
    journey_findings, pressure_series, why_no_journey,
    prompt_occupancy, rooms_seen, repetition,
    slowest_call,
    turn_activity, turn_costs, why_nothing_stands_out, window_pressure,
)
from . import logweb, world
from .cli import PortsBusy, bind, main, serve
from .logview import (
    KNOWN_PHASES, TROUBLE_PHASES, ReadResult, Record, Turn, cost_breakdown,
    follow, group_turns, pair_tools, parse_line, read, totals,
)
from .sessions import (
    DIR_ENV, STATE_DIR, SessionSummary, default_dir, list_sessions, resolve,
    summarize,
)

__all__ = [
    "logweb", "PortsBusy", "bind", "main", "serve",
    "MIN_SAMPLE", "OUTLIER_FACTOR", "PER", "Distribution", "Finding", "attribution",
    "world", "CIRCLING", "GRINDING", "STUCK", "JourneyFinding", "journey_findings", "pressure_series",
    "why_no_journey",
    "cache_saving", "call_durations", "cost_cause", "diff", "findings",
    "prompt_occupancy", "rooms_seen",
    "repetition",
    "slowest_call", "turn_activity", "turn_costs", "why_nothing_stands_out",
    "window_pressure",
    "KNOWN_PHASES", "TROUBLE_PHASES", "ReadResult", "Record", "Turn",
    "cost_breakdown", "follow", "group_turns", "pair_tools", "parse_line",
    "read", "totals",
    "DIR_ENV", "STATE_DIR", "SessionSummary", "default_dir", "list_sessions",
    "resolve", "summarize",
]
