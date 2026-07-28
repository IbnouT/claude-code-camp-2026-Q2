"""Sessions: find the session logs on disk and say enough to pick one.

The question a person actually has is "which run was that", so a summary answers it
with when, what model, how long, what it cost, and how it ended. Everything comes
from the file: the writer is the logger, and this module only reads.

Kept apart from :mod:`logviewer.logview` because choosing a session and reading one
are different jobs. Listing must stay cheap enough to run over a directory of
hundreds of files, so a summary reads the records once and keeps no bodies.

The sessions directory is an ARGUMENT, never resolved by importing the agent's
config. That single import was the viewer's whole coupling to the program it reads,
and a reader meant to outlive its writer cannot depend on the writer to find its
own input. ``default_dir`` resolves the conventional location independently, by the
same documented rules, so the viewer reads a log written by any version.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .logview import Record, read, totals

#: Session filenames are ``<iso-ish timestamp>-<short id>.jsonl``, written by the
#: logger. The timestamp is parsed for display, and a file that does not match still
#: lists: a log is worth reading whatever it is called.
SUFFIX = ".jsonl"


@dataclass
class SessionSummary:
    """One session, described well enough to choose it."""

    id: str
    path: Path
    started_at: datetime | None
    provider: str | None
    model: str | None
    task: str | None
    turns: int
    iterations: int
    calls: int
    tool_calls: int
    input_tokens: int
    output_tokens: int
    peak_input_tokens: int
    cost: float | None
    cost_partial: bool
    failures: int
    compactions: int
    end_reason: str | None
    in_progress: bool

    @property
    def when(self) -> str:
        if self.started_at is None:
            return "unknown"
        return self.started_at.strftime("%Y-%m-%d %H:%M")

    @property
    def outcome(self) -> str:
        """How it ended, in a word a person can scan a column of."""
        if self.in_progress:
            return "in progress"
        if self.end_reason is None:
            return "no turns"
        return self.end_reason

    def render_cost(self) -> str:
        """Money, or an honest absence. Never a zero standing in for unknown."""
        if self.cost is None:
            return "unavailable"
        return f"${self.cost:.4f}" + (" (partial)" if self.cost_partial else "")

    def __str__(self) -> str:
        return (f"<SessionSummary {self.id} turns={self.turns} "
                f"outcome={self.outcome}>")

    __repr__ = __str__


#: Environment variable naming the agent's config directory, the first of the
#: documented resolution rules.
DIR_ENV = "BOUKENSHA_DIR"

#: Directory the agent keeps its state in, searched for while walking up.
STATE_DIR = ".boukensha"


def default_dir(start: str | Path | None = None) -> Path:
    """The conventional sessions directory, resolved without importing anything.

    Follows the same three documented rules the writer uses: the environment
    variable, then the nearest state directory walking up, then the one in the
    home directory. Reimplemented rather than imported because importing it would
    make a reader of logs depend on the program that wrote them, and then a log
    from a version whose config module has moved becomes unreadable.

    Every caller can pass a directory instead, and the launcher does.
    """
    override = os.environ.get(DIR_ENV)
    if override:
        return Path(override).expanduser() / "sessions"
    here = Path(start).resolve() if start else Path.cwd().resolve()
    for candidate in (here, *here.parents):
        if (candidate / STATE_DIR).is_dir():
            return candidate / STATE_DIR / "sessions"
    return Path.home() / STATE_DIR / "sessions"


def _started_at(path: Path, records: list[Record]) -> datetime | None:
    """When the session began: from the filename, else the file's own mtime."""
    stem = path.stem.split("-")[0]
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S"):
        try:
            return datetime.strptime(stem, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None


def summarize(path: str | Path) -> SessionSummary:
    """Read one session file into a summary.

    A file with no ``session_start`` still summarizes: a partially written session is
    a normal thing to want to look at, so the fields it can supply are supplied and
    the rest stay None.
    """
    path = Path(path)
    result = read(path)
    records = result.records
    start = next((r for r in records if r.phase == "session_start"), None)
    figures: dict[str, Any] = totals(records)

    return SessionSummary(
        id=path.stem,
        path=path,
        started_at=_started_at(path, records),
        provider=(start.get("provider") if start else None),
        model=(start.get("model") if start else None),
        task=(start.get("task") if start else None),
        turns=figures["turns"],
        iterations=figures["iterations"],
        calls=figures["calls"],
        tool_calls=figures["tool_calls"],
        input_tokens=figures["input_tokens"],
        output_tokens=figures["output_tokens"],
        peak_input_tokens=figures["peak_input_tokens"],
        cost=figures["cost"],
        cost_partial=figures["cost_partial"],
        failures=figures["failures"],
        compactions=figures["compactions"],
        end_reason=figures["end_reason"],
        # A session whose last turn never ended is still running, or died. Either
        # way it has no ending to report, which is worth saying rather than hiding.
        in_progress=result.incomplete or (
            figures["turns"] > 0 and figures["end_reason"] is None),
    )


def list_sessions(directory: str | Path | None = None) -> list[SessionSummary]:
    """Every session in the directory, newest first.

    An empty or missing directory is an empty list, not an error: having written no
    sessions yet is an ordinary state.
    """
    target = Path(directory) if directory is not None else default_dir()
    if not target.is_dir():
        return []
    files = sorted(target.glob(f"*{SUFFIX}"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    return [summarize(path) for path in files]


def resolve(name: str, directory: str | Path | None = None
            ) -> SessionSummary | None:
    """Find one session by id, by filename, or by ``latest``.

    ``latest`` exists because that is what someone asks for after a run that
    surprised them. A partial id matches when it is unambiguous, since these ids are
    long and nobody types them in full.
    """
    summaries = list_sessions(directory)
    if not summaries:
        return None
    if name in ("latest", "last"):
        return summaries[0]
    for summary in summaries:
        if summary.id == name or summary.path.name == name:
            return summary
    matches = [s for s in summaries if s.id.startswith(name)]
    return matches[0] if len(matches) == 1 else None
