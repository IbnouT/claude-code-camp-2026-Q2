"""Session-static allowlists and generated MCP surface projections."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Iterable, Literal

from .commands import AVAILABLE, BY_NAME, Capability, registry_digest

Projection = Literal["direct", "hybrid"]

CORE_CAPABILITIES = frozenset({
    "attack",
    "check",
    "consider",
    "consume_item",
    "examine",
    "get_item",
    "look",
    "move",
    "mud_status",
    "poll",
    "set_position",
    "shop",
    "skill_strike",
    "track",
})
ALL_AVAILABLE = frozenset(capability.name for capability in AVAILABLE)
DEFAULT_AVAILABLE = ALL_AVAILABLE - {"send_raw"}


class ProfileError(ValueError):
    """Invalid profile configuration."""


class PermissionDenied(Exception):
    """A known capability is not permitted by the session profile."""

    def __init__(self, capability: str, profile_id: str) -> None:
        self.capability = capability
        self.profile_id = profile_id
        super().__init__(
            f"{capability!r} is disabled by gateway profile {profile_id!r}")


class CapabilityUnavailable(Exception):
    """A defined capability has not reached a safe runtime implementation."""


@dataclass(frozen=True)
class Profile:
    """One byte-stable tool policy for an entire session."""

    id: str
    projection: Projection
    allowed: frozenset[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed", frozenset(self.allowed))
        if self.projection not in ("direct", "hybrid"):
            raise ProfileError(
                f"profile {self.id!r} has unknown projection "
                f"{self.projection!r}")
        unknown = self.allowed - set(BY_NAME)
        if unknown:
            raise ProfileError(f"profile {self.id!r} names unknown capabilities: "
                               f"{sorted(unknown)}")
        unavailable = {
            name for name in self.allowed if not BY_NAME[name].available
        }
        if unavailable:
            raise ProfileError(
                f"profile {self.id!r} enables unavailable capabilities: "
                f"{sorted(unavailable)}")

    @property
    def capability_digest(self) -> str:
        return registry_digest(self.allowed)

    def __str__(self) -> str:
        return (
            f"<Profile id={self.id!r} projection={self.projection!r} "
            f"capabilities={len(self.allowed)}>"
        )


PROFILES: dict[str, Profile] = {
    "direct-full": Profile("direct-full", "direct", DEFAULT_AVAILABLE),
    "direct-core": Profile("direct-core", "direct", CORE_CAPABILITIES),
    "hybrid-full": Profile("hybrid-full", "hybrid", DEFAULT_AVAILABLE),
    "hybrid-core": Profile("hybrid-core", "hybrid", CORE_CAPABILITIES),
}


@dataclass(frozen=True)
class Invocation:
    """A surface call resolved to one capability."""

    tool: str
    capability: Capability
    arguments: dict[str, Any]


class Surface:
    """Generated schemas plus server-side enforcement for one profile."""

    def __init__(self, profile: Profile) -> None:
        self.profile = profile
        self._schemas = tuple(self._generate_schemas())

    def schemas(self) -> list[dict[str, Any]]:
        return [deepcopy(schema) for schema in self._schemas]

    @property
    def schema_bytes(self) -> int:
        return len(json.dumps(
            self._schemas,
            sort_keys=True,
            separators=(",", ":"),
        ).encode())

    def measurement(self) -> dict[str, Any]:
        enabled_standard = self.profile.allowed & DEFAULT_AVAILABLE
        return {
            "profile_id": self.profile.id,
            "projection": self.profile.projection,
            "capability_digest": self.profile.capability_digest,
            "enabled_capabilities": len(enabled_standard),
            "available_capabilities": len(DEFAULT_AVAILABLE),
            "coverage": len(enabled_standard) / len(DEFAULT_AVAILABLE),
            "raw_enabled": "send_raw" in self.profile.allowed,
            "advertised_tools": len(self._schemas),
            "schema_bytes": self.schema_bytes,
        }

    def resolve(
            self,
            tool: str,
            arguments: dict[str, Any] | None = None,
    ) -> Invocation:
        given = dict(arguments or {})
        if self.profile.projection == "direct":
            return self._resolve_direct(tool, given)
        return self._resolve_hybrid(tool, given)

    def _resolve_direct(self, tool: str, arguments: dict[str, Any]) -> Invocation:
        capability = BY_NAME.get(tool)
        if capability is None:
            raise ValueError(f"unknown tool: {tool!r}")
        self._authorize(capability)
        return Invocation(tool, capability, capability.validate(arguments))

    def _resolve_hybrid(self, tool: str, arguments: dict[str, Any]) -> Invocation:
        if tool == "move":
            capability = BY_NAME["move"]
            self._authorize(capability)
            return Invocation(tool, capability, capability.validate(arguments))
        if tool not in ("act", "interact"):
            if tool in BY_NAME:
                raise PermissionDenied(tool, self.profile.id)
            raise ValueError(f"unknown tool: {tool!r}")

        action = arguments.get("action")
        if not isinstance(action, str) or not action:
            raise ValueError(f"{tool}: action is required")
        capability = BY_NAME.get(action)
        if capability is None:
            raise ValueError(f"{tool}: unknown action {action!r}")
        if capability.group != tool:
            raise ValueError(
                f"{tool}: {action!r} belongs to the {capability.group!r} group")
        self._authorize(capability)
        nested = arguments.get("arguments", {})
        if not isinstance(nested, dict):
            raise ValueError(f"{tool}: arguments must be an object")
        unknown = set(arguments) - {"action", "arguments"}
        if unknown:
            raise ValueError(f"{tool}: unknown arguments {sorted(unknown)}")
        return Invocation(tool, capability, capability.validate(nested))

    def _authorize(self, capability: Capability) -> None:
        if not capability.available:
            raise CapabilityUnavailable(
                f"{capability.name!r} is defined but not implemented")
        if capability.name not in self.profile.allowed:
            raise PermissionDenied(capability.name, self.profile.id)

    def _generate_schemas(self) -> Iterable[dict[str, Any]]:
        allowed = [
            capability for capability in AVAILABLE
            if capability.name in self.profile.allowed
        ]
        if self.profile.projection == "direct":
            for capability in allowed:
                yield capability.schema()
            return

        if "move" in self.profile.allowed:
            yield BY_NAME["move"].schema()
        for group in ("act", "interact"):
            members = [
                capability for capability in allowed
                if capability.group == group and capability.name != "move"
            ]
            if members:
                yield _group_schema(group, members)

    def __str__(self) -> str:
        return (
            f"<Surface profile={self.profile.id!r} "
            f"tools={len(self._schemas)} bytes={self.schema_bytes}>"
        )


def load_profile(
        profile_id: str | None = None,
        allow: Iterable[str] | None = None,
) -> Profile:
    requested = profile_id or "direct-full"
    try:
        base = PROFILES[requested]
    except KeyError as error:
        raise ProfileError(
            f"unknown gateway profile {requested!r}, expected one of "
            f"{sorted(PROFILES)}") from error

    if allow is None:
        return base

    names = frozenset(allow)
    identity = sha256(
        ",".join(sorted(names)).encode()
    ).hexdigest()[:8]
    return Profile(
        id=f"{base.id}:custom-{identity}",
        projection=base.projection,
        allowed=names,
    )


def _group_schema(group: str, members: list[Capability]) -> dict[str, Any]:
    return {
        "name": group,
        "description": (
            "Run one typed capability. The action selects the operation and "
            "arguments contains that capability's documented fields."
        ),
        "inputSchema": {
            "type": "object",
            "oneOf": [
                {
                    "properties": {
                        "action": {"const": member.name},
                        "arguments": member.schema()["inputSchema"],
                    },
                    "required": (
                        ["action", "arguments"]
                        if any(argument.required for argument in member.arguments)
                        else ["action"]
                    ),
                    "additionalProperties": False,
                }
                for member in members
            ],
        },
    }
