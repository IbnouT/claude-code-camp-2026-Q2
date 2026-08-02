"""Read the observer-owned CircleMUD world at bounded atlas detail."""

from __future__ import annotations

import hashlib
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ..contracts import AtlasNode, AtlasProjection, AtlasZone
from .sector_overrides import (
    DEFAULT_OVERRIDE_PATH,
    default_sector_category,
    load_sector_overrides,
)

DIRECTIONS = ("north", "east", "south", "west", "up", "down")
_DIRECTION_ALIASES = {
    "n": "north",
    "e": "east",
    "s": "south",
    "w": "west",
    "u": "up",
    "d": "down",
}
WORLD_HINT = Path("week0_explore/circlemud-world-parser/assets/wld")
_ROOM = re.compile(r"^#(\d+)\s*$")
_EXIT = re.compile(r"^D([0-5])\s*$")
_TARGET = re.compile(r"^(-?\d+)\s+(-?\d+)\s+(-?\d+)\s*$")
SECTORS = {
    0: "inside",
    1: "city",
    2: "field",
    3: "forest",
    4: "hills",
    5: "mountain",
    6: "water (swimmable)",
    7: "water (not swimmable)",
    8: "flying",
    9: "underwater",
}


@dataclass(frozen=True)
class AtlasRoom:
    """The small atlas subset retained for one source room."""

    vnum: int
    title: str
    zone: int
    sector: str
    exits: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class AtlasLocation:
    """One vnum-correlated observer-truth atlas location."""

    room: AtlasRoom
    zone_label: str
    source_digest: str


class AtlasSource:
    """Cache one measured parse and expose overview or one-zone LOD."""

    def __init__(
        self,
        root: Path | None,
        *,
        override_path: Path | None = DEFAULT_OVERRIDE_PATH,
    ) -> None:
        self._root = root
        self._override_path = override_path
        self._rooms: dict[int, AtlasRoom] | None = None
        self._zone_labels: dict[int, str] | None = None
        self._source_digest: str | None = None
        self._load_ms = 0.0

    @property
    def available(self) -> bool:
        return self._root is not None and self._root.is_dir()

    def projection(
        self,
        *,
        level: str = "overview",
        zone: int | None = None,
    ) -> AtlasProjection:
        if not self.available:
            return AtlasProjection(
                available=False,
                source_state="unavailable",
                source_label="CircleMUD world files",
                level="overview",
                selected_zone=None,
                room_count=0,
                edge_count=0,
                zone_count=0,
                duplicate_title_count=0,
                load_ms=0,
                memory_bytes=0,
                detail=(
                    "No observer world source was found. Set BOUKENSHA_WORLD "
                    "to a directory containing .wld files."
                ),
            )
        rooms = self._load()
        title_counts = Counter(room.title.casefold() for room in rooms.values())
        edge_count = sum(len(room.exits) for room in rooms.values())
        zones: dict[int, list[AtlasRoom]] = defaultdict(list)
        for room in rooms.values():
            zones[room.zone].append(room)
        duplicate_total = sum(1 for count in title_counts.values() if count > 1)
        memory = _memory_size(rooms)
        if level == "zone" and zone is not None:
            selected = zones.get(zone, [])
            nodes = tuple(
                AtlasNode(
                    id=f"room:{room.vnum}",
                    vnum=room.vnum,
                    title=room.title,
                    zone=room.zone,
                    sector=room.sector,
                    exits=room.exits,
                )
                for room in sorted(selected, key=lambda item: item.vnum)
            )
            return AtlasProjection(
                available=True,
                source_state="available",
                source_label="Configured CircleMUD .wld files",
                level="zone",
                selected_zone=zone,
                room_count=len(rooms),
                edge_count=edge_count,
                zone_count=len(zones),
                duplicate_title_count=duplicate_total,
                load_ms=self._load_ms,
                nodes=nodes,
                memory_bytes=memory,
                detail=(
                    f"Zone {zone} contains {len(nodes)} observer-truth rooms. "
                    "No gateway room is correlated without retained vnum evidence."
                ),
            )
        summaries = tuple(
            AtlasZone(
                id=f"zone:{zone_id}",
                zone=zone_id,
                room_count=len(group),
                edge_count=sum(len(room.exits) for room in group),
                duplicate_title_count=sum(
                    1
                    for count in Counter(
                        room.title.casefold() for room in group
                    ).values()
                    if count > 1
                ),
            )
            for zone_id, group in sorted(zones.items())
        )
        return AtlasProjection(
            available=True,
            source_state="available",
            source_label="Configured CircleMUD .wld files",
            level="overview",
            selected_zone=None,
            room_count=len(rooms),
            edge_count=edge_count,
            zone_count=len(zones),
            duplicate_title_count=duplicate_total,
            load_ms=self._load_ms,
            zones=summaries,
            memory_bytes=memory,
            detail=(
                "Observer truth is available as an isolated atlas layer. "
                "Select a zone for room-level detail."
            ),
        )

    def locate(self, vnum: int) -> AtlasLocation | None:
        """Correlate one verified room number without title guessing."""
        rooms = self._load() if self.available else {}
        room = rooms.get(vnum)
        if room is None:
            return None
        labels = self._load_zone_labels()
        label = labels.get(room.zone)
        if label is None:
            return None
        return AtlasLocation(
            room=room,
            zone_label=label,
            source_digest=self._source_digest or "",
        )

    def resolve_unique(
        self,
        title: str,
        exits: tuple[str, ...],
    ) -> AtlasLocation | None:
        """Resolve one unambiguous title and exit signature as an anchor."""

        observed_exits = {
            _DIRECTION_ALIASES.get(direction.casefold(), direction.casefold())
            for direction in exits
        }
        matches = (
            [
                room
                for room in self._load().values()
                if room.title.casefold() == title.casefold()
                and set(room.exits) == observed_exits
            ]
            if self.available
            else []
        )
        if len(matches) != 1:
            return None
        return self.locate(matches[0].vnum)

    def _load(self) -> dict[int, AtlasRoom]:
        if self._rooms is not None:
            return self._rooms
        started = time.perf_counter()
        rooms: dict[int, AtlasRoom] = {}
        digest = hashlib.sha256()
        assert self._root is not None
        for path in sorted(self._root.glob("*.wld")):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            digest.update(path.name.encode())
            digest.update(text.encode())
            rooms.update(_parse(text))
        override_path = self._override_path
        semantic_enabled = override_path is not None and override_path.is_file()
        overrides = load_sector_overrides(override_path)
        if semantic_enabled:
            assert override_path is not None
            digest.update(override_path.read_bytes())
        for vnum, override in overrides.items():
            room = rooms.get(vnum)
            if room is None:
                continue
            if room.sector != override.original_sector:
                raise ValueError(
                    f"Atlas sector override {vnum} expected "
                    f"{override.original_sector!r}, found {room.sector!r}."
                )
        if semantic_enabled:
            rooms = {
                vnum: AtlasRoom(
                    vnum=room.vnum,
                    title=room.title,
                    zone=room.zone,
                    sector=default_sector_category(room.sector),
                    exits=room.exits,
                )
                for vnum, room in rooms.items()
            }
        for vnum, override in overrides.items():
            room = rooms.get(vnum)
            if room is None:
                continue
            rooms[vnum] = AtlasRoom(
                vnum=room.vnum,
                title=room.title,
                zone=room.zone,
                sector=override.corrected_category,
                exits=room.exits,
            )
        self._load_ms = round((time.perf_counter() - started) * 1_000, 3)
        self._rooms = rooms
        self._source_digest = digest.hexdigest()[:20]
        return rooms

    def _load_zone_labels(self) -> dict[int, str]:
        if self._zone_labels is not None:
            return self._zone_labels
        labels: dict[int, str] = {}
        if self._root is None:
            return labels
        candidates = (
            self._root.parent / "zon"
            if self._root.name == "wld"
            else self._root / "zon"
        )
        zone_root = candidates if candidates.is_dir() else self._root
        digest = hashlib.sha256()
        digest.update((self._source_digest or "").encode())
        for path in sorted(zone_root.glob("*.zon")):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            digest.update(path.name.encode())
            digest.update(text.encode())
            parsed = _parse_zone_label(text)
            if parsed is not None:
                labels[parsed[0]] = parsed[1]
        self._zone_labels = labels
        self._source_digest = digest.hexdigest()[:20]
        return labels


def find_world(start: Path | None = None) -> Path | None:
    """Resolve the existing non-secret atlas convention."""

    import os

    override = os.environ.get("BOUKENSHA_WORLD")
    if override:
        candidate = Path(override).expanduser()
        return candidate.resolve() if candidate.is_dir() else None
    here = (start or Path.cwd()).resolve()
    for base in (here, *here.parents):
        candidate = base / WORLD_HINT
        if candidate.is_dir():
            return candidate.resolve()
    return None


def _parse(text: str) -> dict[int, AtlasRoom]:
    rooms: dict[int, AtlasRoom] = {}
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        match = _ROOM.match(lines[index])
        index += 1
        if match is None:
            continue
        vnum = int(match.group(1))
        title = lines[index].rstrip("~").strip() if index < len(lines) else ""
        index += 1
        while index < len(lines) and lines[index].strip() != "~":
            index += 1
        index += 1
        zone = 0
        sector = "unknown"
        if index < len(lines):
            fields = lines[index].split()
            if fields and fields[0].lstrip("-").isdigit():
                zone = int(fields[0])
            if len(fields) >= 3 and fields[2].lstrip("-").isdigit():
                sector_id = int(fields[2])
                sector = SECTORS.get(sector_id, f"unknown ({sector_id})")
            index += 1
        exits: dict[str, int] = {}
        while index < len(lines):
            line = lines[index].strip()
            if line == "S":
                index += 1
                break
            exit_match = _EXIT.match(line)
            if exit_match is None:
                index += 1
                continue
            slot = int(exit_match.group(1))
            index += 1
            terminated = 0
            while index < len(lines) and terminated < 2:
                if lines[index].strip().endswith("~"):
                    terminated += 1
                index += 1
            while index < len(lines):
                target = _TARGET.match(lines[index].strip())
                index += 1
                if target is None:
                    continue
                destination = int(target.group(3))
                if destination >= 0:
                    exits[DIRECTIONS[slot]] = destination
                break
        rooms[vnum] = AtlasRoom(vnum, title, zone, sector, exits)
    return rooms


def _parse_zone_label(text: str) -> tuple[int, str] | None:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = _ROOM.match(line)
        if match is None or index + 1 >= len(lines):
            continue
        label = lines[index + 1].rstrip("~").strip()
        return (int(match.group(1)), label) if label else None
    return None


def _memory_size(rooms: dict[int, AtlasRoom]) -> int:
    total = sys.getsizeof(rooms)
    for key, room in rooms.items():
        total += sys.getsizeof(key) + sys.getsizeof(room)
        total += sys.getsizeof(room.title) + sys.getsizeof(room.exits)
        total += sum(
            sys.getsizeof(direction) + sys.getsizeof(target)
            for direction, target in room.exits.items()
        )
    return total
