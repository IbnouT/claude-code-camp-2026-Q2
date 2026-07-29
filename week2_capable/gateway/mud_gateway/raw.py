"""Audited single-line fallback for explicitly enabled profiles.

An arbitrary line bypasses typed command rendering, so it exists as a named
capability with stronger auditing and is denied by every named profile.

WHY A ROLE RATHER THAN A FLAG. A boolean is one wrong default away from being on. A role has to
be constructed with a value that does not exist on the agent's side of the process, so the
mortal path cannot enable it by getting a configuration wrong. `role` is not a permission check
against a caller's claim about itself, which is why the agent's own claim is never consulted.

WHY IT IS STILL REFUSED FOR SOME INPUT EVEN AS THE HARNESS. Newlines would let one call become
several commands, which turns a logged line into an unlogged batch and makes the journal a lie
about what was sent. That is refused for every role, because the reason has nothing to do with
trust.

Normal profiles deny this capability. The MCP server supplies the trusted role
only after its session-static profile authorizes the call. The caller cannot
claim a role in tool arguments.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from .journal import Journal

#: Anything that would let one call become more than one command, or terminate the line early.
UNSAFE = re.compile(r"[\r\n\x00]")

#: The longest line the game accepts. Beyond it the server truncates, which would make the
#: journal record something different from what the game actually ran.
MAX_LINE = 240


class Role(str, Enum):
    """Which trusted server path authorized the send."""

    HARNESS = "harness"       # the benchmark and the fixtures, which need arbitrary lines
    OPERATOR = "operator"     # a human debugging a live session
    PROFILE = "profile"       # an explicitly allowlisted MCP session


class NotPermitted(Exception):
    """Raised when no trusted server path authorized a raw line."""


@dataclass(frozen=True)
class RawSend:
    """One raw line, with who sent it and why, recorded before it goes out.

    The reason is required. A raw line in a journal with no reason is the one event nobody can
    reconstruct later, because by definition it did not come from a command definition that
    would explain it.
    """

    line: str
    role: Role
    reason: str

    def __str__(self) -> str:
        return f"<RawSend role={self.role.value} reason={self.reason!r} line={self.line!r}>"


def check(line: str, role: object, reason: str) -> RawSend:
    """Validate a raw send, or raise. Nothing is sent by this function.

    Separated from sending so a caller can be tested, and so the refusal path is exercised
    without a connection. The order matters: role first, because an unauthorised caller should
    not learn which lines would have been valid.
    """
    if not isinstance(role, Role):
        raise NotPermitted(
            f"send_raw is not available to {role!r}; the server supplies a trusted "
            "role only after its session profile authorizes the capability")
    if not reason or not reason.strip():
        raise ValueError("a raw send must carry a reason; it is the only record of why")
    if UNSAFE.search(line):
        raise ValueError(
            "a raw line may not contain a newline or a null: one call would become several "
            "commands and the journal would no longer describe what was sent")
    if not line.strip():
        raise ValueError("an empty raw line would be a bare return, which is a menu answer")
    if len(line) > MAX_LINE:
        raise ValueError(f"{len(line)} characters exceeds the {MAX_LINE} the game accepts, and "
                         "the server would truncate it into something else")
    return RawSend(line=line, role=role, reason=reason.strip())


async def send_raw(
        session,
        line: str,
        *,
        role: object,
        reason: str,
        trace_id: str | None = None,
) -> object:
    """Send one arbitrary line. Record its capability gap before it is sent.

    Recorded first so that a line which crashes the connection is still in the record. A raw
    send that only appears in the journal when it succeeded would hide exactly the case anyone
    would go looking for.
    """
    validated = check(line, role, reason)
    journal: Journal = session.journal
    journal.append(
        session.id,
        "capability_gap",
        {
            "line": validated.line,
            "role": validated.role.value,
            "reason": validated.reason,
        },
        trace_id=trace_id,
    )
    return await session.command(validated.line, trace_id=trace_id)
