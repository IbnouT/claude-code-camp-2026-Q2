"""Runtime configuration loaded from explicit environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    gateway_url: str = "http://127.0.0.1:8765"
    runtime_root: Path | None = None
    agent_events: Path | None = None
    benchmark_root: Path | None = None
    experiment_execution_enabled: bool = False
    experiment_max_spend_cap: float = 0
    experiment_state_root: Path | None = None
    world_root: Path | None = None
    copilot_model: str | None = None
    copilot_api_key: str | None = None
    copilot_endpoint: str = "https://api.anthropic.com/v1/messages"
    copilot_spend_cap: float = 0
    copilot_input_rate: float = 0
    copilot_output_rate: float = 0
    voice_api_key: str | None = None
    voice_model: str = "tts-1"
    voice_name: str = "nova"
    voice_endpoint: str = "https://api.openai.com/v1/audio/speech"
    voice_cache_root: Path | None = None
    revision: str = "unknown"
    disabled_features: tuple[str, ...] = ()
    web_dist: Path = Path(__file__).parents[1] / "web" / "dist"

    @classmethod
    def from_environment(cls) -> Settings:
        _load_shared_environment()
        return cls(
            gateway_url=os.environ.get(
                "OBSERVATORY_GATEWAY_URL",
                "http://127.0.0.1:8765",
            ).rstrip("/"),
            runtime_root=_runtime_root(),
            agent_events=_optional_path("OBSERVATORY_AGENT_EVENTS"),
            benchmark_root=_benchmark_root(),
            experiment_execution_enabled=_experiment_execution_enabled(),
            experiment_max_spend_cap=_experiment_max_spend_cap(),
            experiment_state_root=_experiment_state_root(),
            world_root=_world_root(),
            copilot_model=_optional_string(
                "OBSERVATORY_COPILOT_MODEL",
                "copilot",
                "model",
            ),
            copilot_api_key=os.environ.get("ANTHROPIC_API_KEY"),
            copilot_endpoint=_string_value(
                "OBSERVATORY_COPILOT_ENDPOINT",
                "copilot",
                "endpoint",
                default="https://api.anthropic.com/v1/messages",
            ),
            copilot_spend_cap=_float_value(
                "OBSERVATORY_COPILOT_SPEND_CAP",
                "copilot",
                "spend_cap_usd",
            ),
            copilot_input_rate=_float_value(
                "OBSERVATORY_COPILOT_INPUT_RATE",
                "copilot",
                "input_rate_per_million",
            ),
            copilot_output_rate=_float_value(
                "OBSERVATORY_COPILOT_OUTPUT_RATE",
                "copilot",
                "output_rate_per_million",
            ),
            voice_api_key=os.environ.get("OPENAI_API_KEY"),
            voice_model=os.environ.get("TTS_MODEL", "tts-1"),
            voice_name=os.environ.get("TTS_VOICE", "nova"),
            voice_endpoint=os.environ.get(
                "OBSERVATORY_TTS_ENDPOINT",
                "https://api.openai.com/v1/audio/speech",
            ),
            voice_cache_root=_voice_cache_root(),
            revision=os.environ.get("OBSERVATORY_REVISION", "unknown"),
            disabled_features=_disabled_features(),
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


def _load_shared_environment() -> None:
    config_dir = _config_dir()
    if config_dir is None:
        return
    env_file = config_dir / ".env"
    if env_file.is_file():
        load_dotenv(env_file, override=False)


def _runtime_root() -> Path | None:
    explicit = os.environ.get("BOUKENSHA_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    for parent in (Path.cwd(), *Path.cwd().parents):
        candidate = parent / ".boukensha"
        if candidate.is_dir():
            return candidate.resolve()
    return None


def _world_root() -> Path | None:
    from .sources.atlas import find_world

    override = os.environ.get("BOUKENSHA_WORLD")
    if override:
        candidate = Path(override).expanduser()
        return candidate.resolve() if candidate.is_dir() else None
    config_dir = _config_dir()
    if config_dir is not None:
        settings_file = config_dir / "settings.yaml"
        if settings_file.is_file():
            loaded = yaml.safe_load(settings_file.read_text(encoding="utf-8")) or {}
            observatory = loaded.get("observatory", {})
            world = (
                observatory.get("world", {}) if isinstance(observatory, dict) else {}
            )
            configured = world.get("path") if isinstance(world, dict) else None
            if isinstance(configured, str) and configured.strip():
                candidate = Path(configured).expanduser()
                if not candidate.is_absolute():
                    candidate = config_dir.parent / candidate
                return candidate.resolve() if candidate.is_dir() else None
    return find_world()


def _voice_cache_root() -> Path | None:
    override = os.environ.get("OBSERVATORY_TTS_CACHE")
    if override:
        return _resolved_path(override)
    runtime_root = _runtime_root()
    if runtime_root is None:
        return None
    return runtime_root / "cache" / "observatory" / "voice"


def _benchmark_root() -> Path | None:
    override = os.environ.get("OBSERVATORY_BENCHMARK_ROOT")
    if override:
        return _optional_path("OBSERVATORY_BENCHMARK_ROOT")
    configured = _observatory_value("benchmark", "path")
    return _resolved_path(configured) if isinstance(configured, str) else None


def _experiment_execution_enabled() -> bool:
    override = os.environ.get("OBSERVATORY_EXPERIMENT_EXECUTION")
    if override is not None:
        return override.casefold() in {"1", "true", "yes", "on"}
    configured = _observatory_value("experiments", "execution_enabled")
    return configured is True


def _experiment_max_spend_cap() -> float:
    override = os.environ.get("OBSERVATORY_EXPERIMENT_MAX_SPEND_CAP")
    if override is not None:
        return float(override)
    configured = _observatory_value("experiments", "max_spend_cap_usd")
    return float(configured) if isinstance(configured, int | float) else 0


def _experiment_state_root() -> Path | None:
    override = os.environ.get("OBSERVATORY_EXPERIMENT_STATE_ROOT")
    if override:
        return _optional_path("OBSERVATORY_EXPERIMENT_STATE_ROOT")
    configured = _observatory_value("experiments", "state_path")
    return _resolved_path(configured) if isinstance(configured, str) else None


def _optional_string(environment: str, section: str, key: str) -> str | None:
    value = os.environ.get(environment)
    if value is not None:
        return value.strip() or None
    configured = _observatory_value(section, key)
    return (
        configured.strip()
        if isinstance(configured, str) and configured.strip()
        else None
    )


def _string_value(
    environment: str,
    section: str,
    key: str,
    *,
    default: str,
) -> str:
    return _optional_string(environment, section, key) or default


def _float_value(environment: str, section: str, key: str) -> float:
    override = os.environ.get(environment)
    if override is not None:
        return float(override)
    configured = _observatory_value(section, key)
    return float(configured) if isinstance(configured, int | float) else 0


def _disabled_features() -> tuple[str, ...]:
    override = os.environ.get("OBSERVATORY_DISABLED_FEATURES")
    if override is not None:
        return tuple(
            feature.strip() for feature in override.split(",") if feature.strip()
        )
    configured = _observatory_value("", "disabled_features")
    if not isinstance(configured, list):
        return ()
    return tuple(
        feature.strip()
        for feature in configured
        if isinstance(feature, str) and feature.strip()
    )


def _observatory_value(section: str, key: str) -> object:
    config_dir = _config_dir()
    if config_dir is None:
        return None
    settings_file = config_dir / "settings.yaml"
    if not settings_file.is_file():
        return None
    loaded = yaml.safe_load(settings_file.read_text(encoding="utf-8")) or {}
    observatory = loaded.get("observatory", {})
    if not isinstance(observatory, dict):
        return None
    selected = observatory if not section else observatory.get(section, {})
    return selected.get(key) if isinstance(selected, dict) else None


def _resolved_path(value: str) -> Path:
    candidate = Path(value).expanduser()
    config_dir = _config_dir()
    if not candidate.is_absolute() and config_dir is not None:
        candidate = config_dir.parent / candidate
    elif not candidate.is_absolute() and os.environ.get("OBSERVATORY_PROJECT_ROOT"):
        candidate = Path(os.environ["OBSERVATORY_PROJECT_ROOT"]) / candidate
    return candidate.resolve()


def _config_dir() -> Path | None:
    explicit = os.environ.get("BOUKENSHA_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    for parent in (Path.cwd(), *Path.cwd().parents):
        candidate = parent / ".boukensha"
        if candidate.is_dir():
            return candidate.resolve()
    return None
