"""Typed privileged half of a reset for an authenticated mortal session."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Callable

from mud_gateway.admin import AdminSession
from mud_gateway.baseline import DEFAULT_FIELDS, TEMPLE


@dataclass(frozen=True)
class ResetOutcome:
    reset_id: str
    player: str
    session_id: str
    located: tuple[int, str] | None
    drift: dict[str, tuple[object, object]]
    applied: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.drift


class ResetConflict(RuntimeError):
    """The benchmark character is not exclusively owned by the reset process."""


class ResetMutationError(RuntimeError):
    """A privileged reset failed after zero or more mutations."""

    def __init__(
        self,
        message: str,
        *,
        reset_id: str,
        applied: tuple[str, ...],
    ) -> None:
        super().__init__(message)
        self.reset_id = reset_id
        self.applied = applied


class ResetPlan:
    def __init__(
        self,
        fields: dict[str, int] | None = None,
        *,
        room: int = TEMPLE,
        reset_id: str | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> None:
        self.fields = dict(DEFAULT_FIELDS if fields is None else fields)
        self.room = room
        self.reset_id = reset_id
        self.on_progress = on_progress

    async def apply(
        self,
        admin: AdminSession,
        player_name: str,
        *,
        session_id: str,
    ) -> ResetOutcome:
        reset_id = self.reset_id or uuid.uuid4().hex
        journal = admin.journal
        journal.append(
            admin.session.id,
            "reset_started",
            {
                "reset_id": reset_id,
                "player": player_name,
                "session_id": session_id,
                "room": self.room,
            },
        )
        active = await admin.locate_all(player_name)
        if len(active) != 1:
            journal.append(
                admin.session.id,
                "reset_rejected",
                {
                    "reset_id": reset_id,
                    "player": player_name,
                    "reason": "concurrent_session",
                    "active_sessions": len(active),
                },
            )
            raise ResetConflict(
                f"reset requires one active {player_name!r} session, found {len(active)}"
            )
        applied: list[str] = []
        try:
            await admin.restore(player_name)
            self._record(applied, "restore")
            for name, value in self.fields.items():
                await admin.set_field(player_name, name, value)
                self._record(applied, name)
            # Location is applied last. Some character mutations can reload the
            # target, so transferring earlier does not establish the final state.
            await admin.goto(self.room)
            self._record(applied, "goto")
            await admin.transfer(player_name)
            self._record(applied, "transfer")
            located = await admin.locate(player_name)
        except Exception as error:
            journal.append(
                admin.session.id,
                "reset_failed",
                {
                    "reset_id": reset_id,
                    "player": player_name,
                    "session_id": session_id,
                    "applied": applied,
                    "error_type": type(error).__name__,
                },
            )
            raise ResetMutationError(
                str(error),
                reset_id=reset_id,
                applied=tuple(applied),
            ) from error
        drift: dict[str, tuple[object, object]] = {}
        if located is None:
            drift["room"] = (self.room, None)
        elif located[0] != self.room:
            drift["room"] = (self.room, located[0])
        journal.append(
            admin.session.id,
            "reset_applied",
            {
                "reset_id": reset_id,
                "player": player_name,
                "session_id": session_id,
                "ok": not drift,
                "located": located,
                "drift": drift,
                "applied": applied,
            },
        )
        return ResetOutcome(
            reset_id,
            player_name,
            session_id,
            located,
            drift,
            tuple(applied),
        )

    def _record(self, applied: list[str], operation: str) -> None:
        applied.append(operation)
        if self.on_progress is not None:
            self.on_progress(operation)
