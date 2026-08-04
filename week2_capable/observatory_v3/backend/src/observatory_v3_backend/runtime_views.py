"""Behavior-preserving runtime reads and projections."""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import (
    LiveJourneySnapshot,
    LivePlayerStatus,
    RuntimeSessionInvestigation,
)
from .projections.live import derive_player_status, project_live
from .projections.runtime_session import project_runtime_session
from .sources.atlas import AtlasSource
from .sources.runtime import RuntimeSession, RuntimeSource


@dataclass(frozen=True, slots=True)
class RuntimeReadService:
    """Compose retained runtime sources without transport responsibilities."""

    runtime: RuntimeSource
    atlas: AtlasSource

    def session(self, session_id: str) -> RuntimeSession | None:
        """Return one directly addressed runtime session."""
        return self.runtime.session(session_id)

    def live(
        self,
        session_id: str,
        *,
        through: int | None = None,
    ) -> LiveJourneySnapshot | None:
        """Build the existing Live projection for one selected session."""
        selected = self.runtime.session(session_id)
        if selected is None:
            return None
        return project_live(
            selected,
            self.runtime.events(session_id),
            self.runtime.agent_events(session_id),
            through=through,
            atlas=self.atlas,
            operator_messages=self.runtime.operator_messages(session_id),
        )

    def player_status(self, session_id: str) -> LivePlayerStatus:
        """Derive the selected session's observed player state.

        Reads one bounded tail of the session journal, so the roster can show
        vitals without materialization and without loading the full session.
        """
        _, latest = self.runtime.journal_position(session_id)
        events = self.runtime.events(
            session_id,
            after=max(0, latest - 400),
            limit=400,
        )
        vitals_event = next(
            (
                event
                for event in reversed(events)
                if event.kind == "observation"
                and event.payload.get("kind") == "vitals"
            ),
            None,
        )
        return derive_player_status(events, vitals_event)

    def investigation(
        self,
        session_id: str,
    ) -> RuntimeSessionInvestigation | None:
        """Build the existing investigation for one selected session."""
        selected = self.runtime.session(session_id)
        if selected is None:
            return None
        return project_runtime_session(
            selected,
            self.runtime.events(session_id),
            self.runtime.agent_events(session_id),
            atlas=self.atlas,
            operator_messages=self.runtime.operator_messages(session_id),
        )
