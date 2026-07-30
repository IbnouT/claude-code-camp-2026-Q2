from pathlib import Path

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
