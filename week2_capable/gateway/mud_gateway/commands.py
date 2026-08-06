"""Typed mortal capabilities and their game-command renderers.

This registry is the source for validation, direct MCP tools, grouped MCP
tools, profile coverage, and the capability digest. It contains no privileged
command and imports no operator surface.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Literal

DIRECTIONS = ("north", "east", "south", "west", "up", "down")
POSITIONS = ("stand", "sit", "rest", "sleep", "wake")
IMMORTAL = frozenset({
    "advance", "at", "force", "freeze", "goto", "load", "purge", "restore",
    "set", "shutdown", "skillset", "slay", "stat", "switch", "teleport",
    "trans", "transfer", "users", "wizlock",
})

Execution = Literal["wire", "poll", "status", "raw", "routine", "future"]
Group = Literal["act", "interact", "observe", "navigate"]


@dataclass(frozen=True)
class Argument:
    """One validated capability argument."""

    name: str
    kind: str = "string"
    description: str = ""
    required: bool = False
    choices: tuple[str, ...] = ()
    default: str | int | None = None
    item_choices: tuple[str, ...] = ()

    def schema(self) -> dict[str, Any]:
        result: dict[str, Any] = {"type": self.kind}
        if self.description:
            result["description"] = self.description
        if self.choices:
            result["enum"] = list(self.choices)
        if self.default is not None:
            result["default"] = self.default
        if self.kind == "array":
            items: dict[str, Any] = {"type": "string"}
            if self.item_choices:
                items["enum"] = list(self.item_choices)
            result["items"] = items
        return result

    def canonical(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "schema": self.schema(),
            "required": self.required,
        }


@dataclass(frozen=True)
class Capability:
    """One supported mortal operation."""

    name: str
    summary: str
    family: str
    group: Group
    renderer: str
    arguments: tuple[Argument, ...] = ()
    execution: Execution = "wire"
    available: bool = True

    def schema(self, *, tool_name: str | None = None) -> dict[str, Any]:
        properties = {argument.name: argument.schema() for argument in self.arguments}
        required = [argument.name for argument in self.arguments if argument.required]
        input_schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
            "additionalProperties": False,
        }
        if required:
            input_schema["required"] = required
        return {
            "name": tool_name or self.name,
            "description": self.summary,
            "inputSchema": input_schema,
        }

    def validate(self, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        given = dict(arguments or {})
        known = {argument.name for argument in self.arguments}
        unknown = set(given) - known
        if unknown:
            raise ValueError(f"{self.name}: unknown arguments {sorted(unknown)}")

        validated: dict[str, Any] = {}
        for argument in self.arguments:
            value = given.get(argument.name, argument.default)
            if argument.required and value in (None, ""):
                raise ValueError(f"{self.name}: {argument.name} is required")
            if value is None:
                continue
            if argument.kind == "integer":
                if isinstance(value, bool) or not isinstance(value, int):
                    raise ValueError(f"{self.name}: {argument.name} must be an integer")
            elif argument.kind == "array":
                if not isinstance(value, list) or not all(
                        isinstance(item, str) and item for item in value):
                    raise ValueError(
                        f"{self.name}: {argument.name} must be a string array")
                if argument.item_choices:
                    invalid = set(value) - set(argument.item_choices)
                    if invalid:
                        raise ValueError(
                            f"{self.name}: {argument.name} contains {sorted(invalid)}")
            elif not isinstance(value, str):
                raise ValueError(f"{self.name}: {argument.name} must be a string")

            if argument.choices and value not in argument.choices:
                raise ValueError(
                    f"{self.name}: {argument.name}={value!r} is not one of "
                    f"{list(argument.choices)}")
            validated[argument.name] = value
        return validated

    def build(self, arguments: dict[str, Any] | None = None) -> str:
        if self.execution != "wire":
            raise ValueError(f"{self.name} does not send a game command")
        values = self.validate(arguments)
        line = _render(self, values)
        if not _is_mortal(line):
            raise ValueError(f"{self.name} produced a privileged line: {line!r}")
        return line

    def canonical(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "summary": self.summary,
            "family": self.family,
            "group": self.group,
            "renderer": self.renderer,
            "execution": self.execution,
            "available": self.available,
            "arguments": [argument.canonical() for argument in self.arguments],
        }

    def __str__(self) -> str:
        return (
            f"<Capability name={self.name!r} family={self.family!r} "
            f"execution={self.execution!r}>"
        )


def _argument(
        name: str,
        *,
        description: str = "",
        required: bool = False,
        choices: tuple[str, ...] = (),
        default: str | int | None = None,
        kind: str = "string",
        item_choices: tuple[str, ...] = (),
) -> Argument:
    return Argument(
        name=name,
        kind=kind,
        description=description,
        required=required,
        choices=choices,
        default=default,
        item_choices=item_choices,
    )


def _target(description: str = "Target name") -> Argument:
    return _argument("target", description=description, required=True)


CAPABILITIES: tuple[Capability, ...] = (
    Capability(
        "look", "Describe the room or inspect a target.", "perception", "interact",
        "look",
        (
            _argument("target", description="Optional item, creature, or player"),
            _argument(
                "preposition",
                description="How to inspect the target",
                choices=("in", "at", *DIRECTIONS),
            ),
        ),
    ),
    Capability(
        "examine", "Examine a target in detail.", "perception", "interact",
        "verb_target", (_target(),),
    ),
    Capability(
        "check", "Query character or world information.", "self", "interact",
        "single",
        (
            _argument(
                "kind",
                description="Information to query",
                required=True,
                choices=(
                    "score", "inventory", "equipment", "gold", "exits", "time",
                    "weather", "levels", "wimpy", "toggle", "where",
                ),
            ),
        ),
    ),
    Capability(
        "move", "Move one step in a direction.", "movement", "act", "single",
        (_argument("direction", required=True, choices=DIRECTIONS),),
    ),
    Capability("flee", "Attempt to flee combat.", "combat", "act", "literal"),
    Capability(
        "set_position", "Change body position.", "position", "act", "single",
        (_argument("position", required=True, choices=POSITIONS),),
    ),
    Capability(
        "track", "Track a creature or player.", "tracking", "act", "verb_target",
        (_target(),),
    ),
    Capability(
        "attack", "Attack a target using a selected style.", "combat", "act",
        "attack",
        (
            _target(),
            _argument(
                "style",
                description="Attack style",
                choices=("hit", "murder", "kill"),
                default="kill",
            ),
        ),
    ),
    Capability(
        "skill_strike", "Use a combat skill against a target.", "combat", "act",
        "skill",
        (
            _argument(
                "skill",
                required=True,
                choices=("backstab", "bash", "kick", "rescue", "assist"),
            ),
            _target(),
        ),
    ),
    Capability(
        "consider", "Assess a creature before fighting.", "perception", "interact",
        "verb_target", (_target(),),
    ),
    Capability(
        "say", "Speak or emote in the current room.", "social", "interact", "say",
        (
            _argument("text", required=True),
            _argument(
                "mode", choices=("say", "emote", "reply"), default="say"),
        ),
    ),
    Capability(
        "tell", "Send a private message.", "social", "interact", "tell",
        (
            _target("Player name"),
            _argument("text", required=True),
            _argument(
                "mode", choices=("tell", "whisper", "ask"), default="tell"),
        ),
    ),
    Capability(
        "channel_say", "Broadcast over a global channel.", "social", "interact",
        "channel",
        (
            _argument(
                "channel",
                required=True,
                choices=("shout", "gossip", "auction", "grats", "holler"),
            ),
            _argument("text", required=True),
        ),
    ),
    Capability(
        "get_item", "Pick up an item, optionally from a container.", "items", "act",
        "get",
        (
            _argument("item", required=True),
            _argument("count", kind="integer"),
            _argument("container"),
        ),
    ),
    Capability(
        "drop_item", "Drop, donate, or junk an item.", "items", "act", "drop",
        (
            _argument("item", required=True),
            _argument("count", kind="integer"),
            _argument(
                "mode", choices=("drop", "donate", "junk"), default="drop"),
        ),
    ),
    Capability(
        "put_item", "Put an item into a container.", "items", "act", "put",
        (
            _argument("item", required=True),
            _argument("container", required=True),
            _argument("count", kind="integer"),
        ),
    ),
    Capability(
        "equip_item", "Wear, wield, hold, grab, or remove an item.", "items", "act",
        "equip",
        (
            _argument("item", required=True),
            _argument(
                "action",
                required=True,
                choices=("wear", "wield", "grab", "hold", "remove"),
            ),
            _argument("body_loc"),
        ),
    ),
    Capability(
        "consume_item", "Eat, drink, taste, or sip an item.", "items", "act",
        "consume",
        (
            _argument("item", required=True),
            _argument(
                "mode", choices=("eat", "taste", "drink", "sip"), default="eat"),
        ),
    ),
    Capability(
        "cast_spell", "Cast a spell, optionally at a target.", "magic", "act",
        "cast",
        (
            _argument("spell", required=True),
            _argument("target"),
        ),
    ),
    Capability(
        "use_magic_item", "Activate a potion, scroll, wand, or staff.", "magic",
        "act", "magic_item",
        (
            _argument("item", required=True),
            _argument("mode", required=True, choices=("use", "quaff", "recite")),
            _argument("target_args"),
        ),
    ),
    Capability(
        "shop", "List, buy, sell, value, or offer shop goods.", "commerce",
        "interact", "shop",
        (
            _argument(
                "action",
                required=True,
                choices=("buy", "sell", "list", "value", "offer"),
            ),
            _argument("args"),
        ),
    ),
    Capability(
        "practice", "List skills or practice one skill.", "training", "act",
        "practice", (_argument("skill"),),
    ),
    Capability(
        "save_character", "Save character progress.", "lifecycle", "act", "save"),
    Capability(
        "poll", "Return output that arrived while idle.", "status", "interact",
        "none", execution="poll"),
    Capability(
        "mud_status", "Report whether the game session is connected.", "status",
        "interact", "none", execution="status"),
    Capability(
        "send_raw", "Send one audited game line as an explicit fallback.", "fallback",
        "act", "none",
        (
            _argument("line", description="One game command line", required=True),
            _argument(
                "reason",
                description="Why no typed capability can perform this operation",
                required=True,
            ),
        ),
        execution="raw",
    ),
    Capability(
        "observe", "Read trustworthy structured current state.", "observation",
        "observe", "none",
        (
            _argument(
                "query",
                choices=("current", "room", "self", "events"),
                default="current",
            ),
        ),
        execution="future",
        available=False,
    ),
    Capability(
        "navigate", "Follow steps until a declared guard stops execution.",
        "movement", "navigate", "none",
        (
            _argument(
                "steps",
                kind="array",
                required=True,
                item_choices=DIRECTIONS,
            ),
            _argument(
                "stop_conditions",
                kind="array",
                required=True,
                item_choices=(
                    "blocked_exit", "combat", "low_vitals", "unexpected_room",
                    "priority_interrupt",
                ),
            ),
        ),
        execution="future",
        available=False,
    ),
    Capability(
        "recall_state",
        "Summarize the current place, exits, vitals, and map coverage "
        "from retained knowledge. Costs no game command.",
        "perception", "interact", "none",
        (),
        execution="routine",
        available=False,
    ),
    Capability(
        "sweep",
        "Explore unmapped ground from the learned frontier until a bound "
        "or an interrupt stops the walk.",
        "movement", "navigate", "none",
        (),
        execution="routine",
        available=False,
    ),
    Capability(
        "travel_to",
        "Walk a computed route over the learned map to a room named by "
        "its remembered title.",
        "movement", "navigate", "none",
        (
            _argument("destination", required=True),
        ),
        execution="routine",
        available=False,
    ),
)

BY_NAME: dict[str, Capability] = {
    capability.name: capability for capability in CAPABILITIES
}
AVAILABLE = tuple(capability for capability in CAPABILITIES if capability.available)


def registry_digest(names: set[str] | frozenset[str] | None = None) -> str:
    selected = CAPABILITIES if names is None else tuple(
        capability for capability in CAPABILITIES if capability.name in names)
    body = json.dumps(
        [capability.canonical() for capability in selected],
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return sha256(body).hexdigest()[:16]


def build(name: str, arguments: dict[str, Any] | None = None) -> str:
    capability = BY_NAME.get(name)
    if capability is None:
        raise ValueError(f"no such capability: {name!r}")
    return capability.build(arguments)


def _render(capability: Capability, values: dict[str, Any]) -> str:
    renderer = capability.renderer
    if renderer == "literal":
        return "flee"
    if renderer == "save":
        return "save"
    if renderer == "single":
        return str(next(iter(values.values())))
    if renderer == "look":
        preposition = values.get("preposition")
        target = values.get("target")
        if preposition and not target:
            raise ValueError("look: preposition requires target")
        return " ".join(str(part) for part in ("look", preposition, target) if part)
    if renderer == "verb_target":
        return f"{capability.name} {values['target']}"
    if renderer == "attack":
        return f"{values['style']} {values['target']}"
    if renderer == "skill":
        return f"{values['skill']} {values['target']}"
    if renderer == "say":
        return f"{values['mode']} {values['text']}"
    if renderer == "tell":
        return f"{values['mode']} {values['target']} {values['text']}"
    if renderer == "channel":
        return f"{values['channel']} {values['text']}"
    if renderer == "get":
        return _parts("get", values.get("count"), values["item"], values.get("container"))
    if renderer == "drop":
        return _parts(values["mode"], values.get("count"), values["item"])
    if renderer == "put":
        return _parts("put", values.get("count"), values["item"], values["container"])
    if renderer == "equip":
        return _parts(values["action"], values["item"], values.get("body_loc"))
    if renderer == "consume":
        return f"{values['mode']} {values['item']}"
    if renderer == "cast":
        return _parts("cast", f"'{values['spell']}'", values.get("target"))
    if renderer == "magic_item":
        return _parts(values["mode"], values["item"], values.get("target_args"))
    if renderer == "shop":
        return _parts(values["action"], values.get("args"))
    if renderer == "practice":
        return _parts("practice", values.get("skill"))
    raise ValueError(f"unknown command renderer: {renderer!r}")


def _parts(*parts: object) -> str:
    return " ".join(str(part) for part in parts if part not in (None, ""))


def _is_mortal(line: str) -> bool:
    first = re.split(r"\s+", line.strip().lower())[0] if line.strip() else ""
    return bool(first) and first not in IMMORTAL
