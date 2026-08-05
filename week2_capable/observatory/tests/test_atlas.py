import json
from pathlib import Path

import pytest

from backend.sources.atlas import AtlasSource


def test_repository_atlas_meets_actual_scale_budget():
    root = (
        Path(__file__).resolve().parents[3]
        / "week0_explore"
        / "circlemud-world-parser"
        / "assets"
        / "wld"
    )
    projection = AtlasSource(root, override_path=None).projection()
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

    location = AtlasSource(root, override_path=None).locate(3001)

    assert location is not None
    assert location.room.title == "The Temple Of Midgaard"
    assert location.room.zone == 30
    assert location.room.sector == "inside"
    assert location.zone_label == "Northern Midgaard Main City"
    assert len(location.source_digest) == 20


@pytest.mark.parametrize(
    ("vnum", "category"),
    [
        (3059, "route"),
        (5139, "interior"),
        (7104, "underground"),
        (3005, "urban"),
        (3154, "open-land"),
        (2525, "water"),
        (4039, "highland"),
        (6068, "woodland"),
        (3007, "commerce"),
        (3004, "civic"),
        (3001, "sacred"),
        (0, "special"),
    ],
)
def test_repository_atlas_projects_each_frozen_semantic_category(
    vnum: int,
    category: str,
):
    root = (
        Path(__file__).resolve().parents[3]
        / "week0_explore"
        / "circlemud-world-parser"
        / "assets"
        / "wld"
    )

    location = AtlasSource(root).locate(vnum)

    assert location is not None
    assert location.room.sector == category


def test_repository_atlas_projection_uses_only_the_frozen_vocabulary():
    root = (
        Path(__file__).resolve().parents[3]
        / "week0_explore"
        / "circlemud-world-parser"
        / "assets"
        / "wld"
    )
    source = AtlasSource(root)
    overview = source.projection()

    categories = {
        node.sector
        for zone in overview.zones
        for node in source.projection(level="zone", zone=zone.zone).nodes
    }

    assert categories == {
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


def test_atlas_applies_an_explicit_semantic_override(tmp_path: Path):
    world = tmp_path / "wld"
    world.mkdir()
    (world / "test.wld").write_text(
        "#100\nGuild Hall~\nA public guild office.\n~\n7 0 1\nS\n$\n",
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
                        "corrected_category": "civic",
                        "rationale": "title and description identify a guild",
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
    assert corrected.nodes[0].sector == "civic"


def test_atlas_maps_an_unlisted_raw_sector_when_semantics_are_enabled(
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
        json.dumps({"version": 1, "overrides": []}),
        encoding="utf-8",
    )

    raw = AtlasSource(world, override_path=None).projection(
        level="zone",
        zone=7,
    )
    semantic = AtlasSource(
        world,
        override_path=override_path,
    ).projection(level="zone", zone=7)

    assert raw.nodes[0].sector == "city"
    assert semantic.nodes[0].sector == "urban"


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
