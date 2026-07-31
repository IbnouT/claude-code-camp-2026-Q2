import json
from pathlib import Path

import pytest

from observatory_api.sources.atlas import AtlasSource


def test_repository_atlas_meets_actual_scale_budget():
    root = (
        Path(__file__).resolve().parents[3]
        / "week0_explore"
        / "circlemud-world-parser"
        / "assets"
        / "wld"
    )
    projection = AtlasSource(root).projection()
    assert projection.available
    assert projection.room_count == 1_878
    assert projection.edge_count == 4_293
    assert projection.zone_count == 33
    assert projection.duplicate_title_count == 241
    assert projection.load_ms < 250
    assert projection.memory_bytes < 8 * 1024 * 1024
    assert len(projection.zones) == 33


def test_atlas_correlates_a_vnum_with_its_zone_label_and_raw_sector():
    root = (
        Path(__file__).resolve().parents[3]
        / "week0_explore"
        / "circlemud-world-parser"
        / "assets"
        / "wld"
    )

    location = AtlasSource(root).locate(3001)

    assert location is not None
    assert location.room.title == "The Temple Of Midgaard"
    assert location.room.zone == 30
    assert location.room.sector == "inside"
    assert location.zone_label == "Northern Midgaard Main City"
    assert len(location.source_digest) == 20


def test_atlas_applies_an_explicit_semantic_override(tmp_path: Path):
    world = tmp_path / "wld"
    world.mkdir()
    (world / "test.wld").write_text(
        "#100\nTown Square~\nAn open square.\n~\n7 0 1\nS\n$\n",
        encoding="utf-8",
    )
    override_path = tmp_path / "overrides.json"
    override_path.write_text(
        json.dumps(
            {
                "version": 1,
                "overrides": [
                    {
                        "vnum": 100,
                        "original_sector": "city",
                        "corrected_category": "urban",
                        "rationale": "title and description identify a plaza",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    raw = AtlasSource(world, override_path=None).projection(
        level="zone",
        zone=7,
    )
    corrected = AtlasSource(
        world,
        override_path=override_path,
    ).projection(level="zone", zone=7)

    assert raw.nodes[0].sector == "city"
    assert corrected.nodes[0].sector == "urban"


def test_atlas_rejects_an_override_for_a_different_source_sector(
    tmp_path: Path,
):
    world = tmp_path / "wld"
    world.mkdir()
    (world / "test.wld").write_text(
        "#100\nTown Square~\nAn open square.\n~\n7 0 1\nS\n$\n",
        encoding="utf-8",
    )
    override_path = tmp_path / "overrides.json"
    override_path.write_text(
        json.dumps(
            {
                "version": 1,
                "overrides": [
                    {
                        "vnum": 100,
                        "original_sector": "inside",
                        "corrected_category": "urban",
                        "rationale": "title and description identify a plaza",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="expected 'inside', found 'city'"):
        AtlasSource(world, override_path=override_path).projection()
