"""Runtime configuration loaded from explicit environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    gateway_url: str = "http://127.0.0.1:8765"
    agent_events: Path | None = None
    benchmark_root: Path | None = None
    knowledge_db: Path | None = None
    web_dist: Path = Path(__file__).parents[1] / "web" / "dist"

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            gateway_url=os.environ.get(
                "OBSERVATORY_GATEWAY_URL",
                "http://127.0.0.1:8765",
            ).rstrip("/"),
            agent_events=_optional_path("OBSERVATORY_AGENT_EVENTS"),
            benchmark_root=_optional_path("OBSERVATORY_BENCHMARK_ROOT"),
            knowledge_db=_optional_path("OBSERVATORY_KNOWLEDGE_DB"),
            web_dist=Path(
                os.environ.get(
                    "OBSERVATORY_WEB_DIST",
                    str(Path(__file__).parents[1] / "web" / "dist"),
                )
            ),
        )


def _optional_path(name: str) -> Path | None:
    value = os.environ.get(name)
    return None if value is None else Path(value)
