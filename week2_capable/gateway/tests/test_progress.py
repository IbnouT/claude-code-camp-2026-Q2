"""Progress read from what the game reported, never from prose."""

from __future__ import annotations

import time
from pathlib import Path

from mud_gateway.knowledge import KnowledgeStore
from mud_gateway.knowledge_models import EvidenceRef
from mud_gateway.progress import read


def _record(store: KnowledgeStore, name: str, values, start: float = 1000.0):
    for offset, value in enumerate(values):
        store.assert_fact(
            "player:tester",
            f"state.{name}",
            value,
            layer="parsed",
            confidence="high",
            evidence=EvidenceRef(
                session_id="s1", source_seq=offset + 1,
                wire_digest="d" * 64, parser_version="1",
                method="score", observed_at=start + offset,
            ),
        )


def _store(tmp_path: Path) -> KnowledgeStore:
    return KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")


def test_experience_gained_is_the_sum_of_the_steps(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _record(store, "exp", [100, 140, 175])
    progress = read(store, "tester")
    store.close()

    assert progress.experience_gained == 75
    assert progress.recent_gains(2) == (40, 35)


def test_losing_experience_is_not_counted_as_a_gain(tmp_path: Path) -> None:
    """Dying costs experience, and a loss must not read as progress."""
    store = _store(tmp_path)
    _record(store, "exp", [100, 140, 90])
    progress = read(store, "tester")
    store.close()

    assert progress.experience_gained == 40


def test_falling_gains_are_recognised(tmp_path: Path) -> None:
    """Steps that shrink at a steady reading pace mean the prey is outgrown."""
    store = _store(tmp_path)
    _record(store, "exp", [0, 50, 100, 150, 160, 170, 180])
    progress = read(store, "tester")
    store.close()

    assert progress.gains_per_reading_are_falling() is True


def test_steady_gains_are_not_falling(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _record(store, "exp", [0, 50, 100, 150, 200, 250, 300])
    progress = read(store, "tester")
    store.close()

    assert progress.gains_per_reading_are_falling() is False


def test_too_few_gains_to_judge_says_nothing(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _record(store, "exp", [0, 50])
    progress = read(store, "tester")
    store.close()

    assert progress.gains_per_reading_are_falling() is False


def test_levels_and_gold_are_counted_too(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _record(store, "level", [1, 1, 2])
    _record(store, "gold", [0, 30, 25])
    progress = read(store, "tester")
    store.close()

    assert progress.levels_gained == 1
    assert progress.gold_gained == 30


def test_reading_the_score_less_often_is_not_a_richer_hunt(
    tmp_path: Path,
) -> None:
    """The same prey, checked twice as often, must not read as decline.

    Each step is the ground between two readings, so halving the pace
    halves every step. Nothing about the hunting changed.
    """
    store = _store(tmp_path)
    _record(store, "exp", [0, 100, 200, 300, 350, 400, 450])
    progress = read(store, "tester")
    store.close()

    assert progress.gains_per_reading_are_falling() is True, (
        "this is the trap: identical prey, only the reading pace changed"
    )
