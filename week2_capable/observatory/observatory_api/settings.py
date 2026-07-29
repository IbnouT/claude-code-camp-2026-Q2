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
    copilot_model: str | None = None
    copilot_api_key: str | None = None
    copilot_endpoint: str = "https://api.anthropic.com/v1/messages"
    copilot_spend_cap: float = 0
    copilot_input_rate: float = 0
    copilot_output_rate: float = 0
    revision: str = "unknown"
    disabled_features: tuple[str, ...] = ()
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
            copilot_model=os.environ.get("OBSERVATORY_COPILOT_MODEL"),
            copilot_api_key=os.environ.get("ANTHROPIC_API_KEY"),
            copilot_endpoint=os.environ.get(
                "OBSERVATORY_COPILOT_ENDPOINT",
                "https://api.anthropic.com/v1/messages",
            ),
            copilot_spend_cap=float(
                os.environ.get("OBSERVATORY_COPILOT_SPEND_CAP", "0")
            ),
            copilot_input_rate=float(
                os.environ.get("OBSERVATORY_COPILOT_INPUT_RATE", "0")
            ),
            copilot_output_rate=float(
                os.environ.get("OBSERVATORY_COPILOT_OUTPUT_RATE", "0")
            ),
            revision=os.environ.get("OBSERVATORY_REVISION", "unknown"),
            disabled_features=tuple(
                feature.strip()
                for feature in os.environ.get(
                    "OBSERVATORY_DISABLED_FEATURES",
                    "",
                ).split(",")
                if feature.strip()
            ),
            web_dist=Path(
                os.environ.get(
                    "OBSERVATORY_WEB_DIST",
                    str(Path(__file__).parents[1] / "web" / "dist"),
                )
            ),
        )


def _optional_path(name: str) -> Path | None:
    value = os.environ.get(name)
    if value is None:
        return None
    path = Path(value)
    project_root = os.environ.get("OBSERVATORY_PROJECT_ROOT")
    if not path.is_absolute() and project_root:
        return Path(project_root) / path
    return path
