import json
from pathlib import Path

import pytest

from backend.sources.sector_overrides import (
    SectorOverride,
    default_sector_category,
    load_sector_overrides,
)


def _row(
    *,
    vnum: int = 100,
    category: str = "urban",
) -> dict[str, object]:
    return {
        "vnum": vnum,
        "original_sector": "city",
        "corrected_category": category,
        "rationale": "title and description identify an outdoor plaza",
    }


def _write_artifact(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        json.dumps({"version": 1, "overrides": rows}),
        encoding="utf-8",
    )


def test_sector_override_loader_accepts_a_valid_disagreement(tmp_path: Path):
    path = tmp_path / "overrides.json"
    _write_artifact(path, [_row()])

    assert load_sector_overrides(path) == {
        100: SectorOverride(
            vnum=100,
            original_sector="city",
            corrected_category="urban",
            rationale="title and description identify an outdoor plaza",
        )
    }


def test_sector_override_loader_treats_an_absent_artifact_as_raw_fallback(
    tmp_path: Path,
):
    assert load_sector_overrides(tmp_path / "missing.json") == {}


@pytest.mark.parametrize(
    ("raw_sector", "category"),
    [
        ("inside", "interior"),
        ("city", "urban"),
        ("field", "open-land"),
        ("forest", "woodland"),
        ("hills", "highland"),
        ("mountain", "highland"),
        ("water (swimmable)", "water"),
        ("water (not swimmable)", "water"),
        ("flying", "special"),
        ("underwater", "water"),
    ],
)
def test_default_sector_category_projects_known_engine_terrain(
    raw_sector: str,
    category: str,
):
    assert default_sector_category(raw_sector) == category


def test_default_sector_category_preserves_an_unknown_engine_sector():
    assert default_sector_category("unknown (12)") == "unknown (12)"


def test_sector_override_loader_rejects_malformed_json(tmp_path: Path):
    path = tmp_path / "overrides.json"
    path.write_text('{"version": 1,', encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        load_sector_overrides(path)


def test_sector_override_loader_rejects_invalid_row_fields(tmp_path: Path):
    path = tmp_path / "overrides.json"
    row = _row()
    row["unreviewed"] = True
    _write_artifact(path, [row])

    with pytest.raises(ValueError, match="fields are invalid"):
        load_sector_overrides(path)


def test_sector_override_loader_rejects_duplicate_vnums(tmp_path: Path):
    path = tmp_path / "overrides.json"
    _write_artifact(path, [_row(), _row()])

    with pytest.raises(ValueError, match="vnum 100 is duplicated"):
        load_sector_overrides(path)


def test_sector_override_loader_rejects_an_unknown_category(tmp_path: Path):
    path = tmp_path / "overrides.json"
    _write_artifact(path, [_row(category="unknown")])

    with pytest.raises(ValueError, match="unknown category"):
        load_sector_overrides(path)
