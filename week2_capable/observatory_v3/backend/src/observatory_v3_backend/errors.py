"""Typed failures raised by retained-evidence repositories."""

from __future__ import annotations

from pathlib import Path


class ObservatoryRepositoryError(RuntimeError):
    """Base class for repository failures safe to translate at the API edge."""


class SourceUnavailableError(ObservatoryRepositoryError):
    """A required retained source does not exist."""

    def __init__(self, source: Path) -> None:
        self.source = source
        super().__init__(f"retained source is unavailable: {source}")


class UnsupportedSchemaError(ObservatoryRepositoryError):
    """A retained database has a schema version this reader cannot consume."""

    def __init__(self, source: Path, *, actual: int, expected: int) -> None:
        self.source = source
        self.actual = actual
        self.expected = expected
        super().__init__(
            f"unsupported schema for {source.name}: found {actual}, expected {expected}"
        )


class MalformedSourceError(ObservatoryRepositoryError):
    """A retained source violates its declared schema or encoding."""

    def __init__(self, source: Path, detail: str) -> None:
        self.source = source
        self.detail = detail
        super().__init__(f"malformed retained source {source.name}: {detail}")


class PathIdentityError(ObservatoryRepositoryError):
    """A registry path does not belong to the declared player and session."""

    def __init__(self, source: Path, detail: str) -> None:
        self.source = source
        self.detail = detail
        super().__init__(f"invalid retained path {source}: {detail}")
