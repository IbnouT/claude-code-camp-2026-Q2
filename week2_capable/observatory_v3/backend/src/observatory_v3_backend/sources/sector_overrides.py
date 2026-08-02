"""Load the frozen observer-owned semantic sector corrections."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

SECTOR_CATEGORIES = frozenset(
    {
        "route",
        "interior",
        "underground",
        "urban",
        "open-land",
        "water",
        "highland",
        "woodland",
        "commerce",
        "civic",
        "sacred",
        "special",
    }
)
DEFAULT_OVERRIDE_PATH = Path(__file__).with_name("atlas_sector_overrides.json")
DEFAULT_SECTOR_CATEGORIES = {
    "inside": "interior",
    "city": "urban",
    "field": "open-land",
    "forest": "woodland",
    "hills": "highland",
    "mountain": "highland",
    "water (swimmable)": "water",
    "water (not swimmable)": "water",
    "flying": "special",
    "underwater": "water",
}


@dataclass(frozen=True)
class SectorOverride:
    """One reviewed correction that leaves the source world untouched."""

    vnum: int
    original_sector: str
    corrected_category: str
    rationale: str


def default_sector_category(raw_sector: str) -> str:
    """Project one known engine sector into the observer vocabulary."""

    return DEFAULT_SECTOR_CATEGORIES.get(raw_sector, raw_sector)


def load_sector_overrides(
    path: Path | None = DEFAULT_OVERRIDE_PATH,
) -> dict[int, SectorOverride]:
    """Validate and index the frozen disagreement-only artifact."""

    if path is None or not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("version") != 1:
        raise ValueError("Atlas sector overrides must use schema version 1.")
    rows = value.get("overrides")
    if not isinstance(rows, list):
        raise ValueError("Atlas sector overrides must contain an overrides list.")

    overrides: dict[int, SectorOverride] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "vnum",
            "original_sector",
            "corrected_category",
            "rationale",
        }:
            raise ValueError("Atlas sector override fields are invalid.")
        vnum = row["vnum"]
        original_sector = row["original_sector"]
        corrected_category = row["corrected_category"]
        rationale = row["rationale"]
        if not isinstance(vnum, int) or vnum < 0:
            raise ValueError("Atlas sector override vnum is invalid.")
        if vnum in overrides:
            raise ValueError(f"Atlas sector override vnum {vnum} is duplicated.")
        if not isinstance(original_sector, str) or not original_sector:
            raise ValueError(f"Atlas sector override {vnum} lacks an original sector.")
        if corrected_category not in SECTOR_CATEGORIES:
            raise ValueError(f"Atlas sector override {vnum} has an unknown category.")
        if not isinstance(rationale, str) or not rationale:
            raise ValueError(f"Atlas sector override {vnum} lacks a rationale.")
        overrides[vnum] = SectorOverride(
            vnum=vnum,
            original_sector=original_sector,
            corrected_category=corrected_category,
            rationale=rationale,
        )
    return overrides
