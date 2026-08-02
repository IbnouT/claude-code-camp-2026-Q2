"""Behavior-preserving runtime reads and projections."""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import LiveJourneySnapshot, RuntimeSessionInvestigation
from .projections.live import project_live
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
