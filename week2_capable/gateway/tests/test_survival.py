from __future__ import annotations

import asyncio
import time
from pathlib import Path

from mud_gateway.knowledge import KnowledgeStore
from mud_gateway.knowledge_models import EvidenceRef
from mud_gateway.survival import Survival


class _Journal:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def append(self, session, kind, payload, trace_id=None):
        self.events.append((kind, payload))


class _Vitals:
    def __init__(self, move: int) -> None:
        self.move = move


class _Reply:
    def __init__(self, move: int | None = None, text: str = "") -> None:
        self.observations = (_Vitals(move),) if move is not None else ()
        self.text = text


class _Session:
    def __init__(self, score_moves: list[int], toggles: str = "") -> None:
        self.id = "fake"
        self.journal = _Journal()
        self.commands: list[str] = []
        self.score_moves = list(score_moves)
        self.toggles = toggles

    async def command(self, line: str, trace_id=None) -> _Reply:
        self.commands.append(line)
        if line == "score" and self.score_moves:
            return _Reply(self.score_moves.pop(0))
        if line == "toggle":
            return _Reply(text=self.toggles)
        return _Reply()


def _store_with_maxima(tmp_path: Path, **maxima: int) -> KnowledgeStore:
    store = KnowledgeStore(tmp_path / "knowledge.db", player_id="tester")
    evidence = EvidenceRef(
        session_id="test", source_seq=1, wire_digest="d",
        parser_version="p1", method="test", observed_at=time.time(),
    )
    for name, value in maxima.items():
        store.assert_fact(
            "player:tester", f"state.max_{name}", value,
            layer="parsed", confidence="confirmed",
            evidence=evidence, transaction_id="t1",
        )
    return store


def test_wimpy_is_set_from_observed_maximum_hp(tmp_path: Path) -> None:
    store = _store_with_maxima(tmp_path, hit=46)
    session = _Session([])
    threshold = asyncio.run(Survival(session, store).apply_wimpy())
    store.close()
    assert threshold == 13
    assert session.commands == ["wimpy 13"]
    kinds = [payload["rule"] for kind, payload in session.journal.events]
    assert kinds == ["wimpy"]


def test_wimpy_declines_honestly_without_a_maximum(tmp_path: Path) -> None:
    store = _store_with_maxima(tmp_path)
    session = _Session([])
    threshold = asyncio.run(Survival(session, store).apply_wimpy())
    store.close()
    assert threshold is None
    assert session.commands == []
    assert session.journal.events[0][1]["applied"] is False


def test_rest_recovers_then_stands(tmp_path: Path) -> None:
    store = _store_with_maxima(tmp_path, move=84)
    session = _Session(score_moves=[30, 70])
    survival = Survival(
        session, store,
        {"rest_poll_seconds": 0, "rest_threshold": 0.2, "rest_resume": 0.8},
    )
    outcome = asyncio.run(survival.recover_movement(10))
    store.close()
    assert outcome == "rested"
    assert session.commands == ["rest", "score", "score", "stand"]


def test_rest_gives_up_after_its_bounded_wait(tmp_path: Path) -> None:
    store = _store_with_maxima(tmp_path, move=84)
    session = _Session(score_moves=[20] * 30)
    survival = Survival(
        session, store,
        {"rest_poll_seconds": 0, "rest_max_polls": 3},
    )
    outcome = asyncio.run(survival.recover_movement(5))
    store.close()
    assert outcome == "rest_timeout"
    assert session.commands.count("score") == 3
    assert session.commands[-1] == "stand"


def test_no_rest_needed_above_the_floor(tmp_path: Path) -> None:
    store = _store_with_maxima(tmp_path, move=84)
    session = _Session([])
    outcome = asyncio.run(Survival(session, store).recover_movement(60))
    store.close()
    assert outcome is None
    assert session.commands == []


def test_the_game_is_asked_to_loot_for_us(tmp_path: Path) -> None:
    """A corpse looted by the game costs no decision after every kill."""
    session = _Session([], toggles="AutoLoot: OFF  AutoGold: OFF  Autodoor: OFF  Autokey: OFF")
    store = _store_with_maxima(tmp_path)
    survival = Survival(session, store, {})

    applied = asyncio.run(survival.let_the_game_do_the_work())

    assert applied == ("autoloot", "autogold", "autodoor", "autokey")
    assert session.commands[0] == "toggle", "read the switches before setting"
    store.close()


def test_the_toggles_are_settings(tmp_path: Path) -> None:
    session = _Session([], toggles="AutoLoot: OFF")
    store = _store_with_maxima(tmp_path)
    survival = Survival(session, store, {"game_toggles": ("autoloot",)})

    asyncio.run(survival.let_the_game_do_the_work())

    assert session.commands == ["toggle", "autoloot"]
    store.close()


def test_something_already_on_is_left_alone(tmp_path: Path) -> None:
    """These switches are remembered, so setting one that is on turns it off."""
    session = _Session([], toggles="AutoLoot: ON  AutoGold: ON  Autodoor: ON  Autokey: ON")
    store = _store_with_maxima(tmp_path)

    changed = asyncio.run(
        Survival(session, store, {}).let_the_game_do_the_work()
    )
    store.close()

    assert changed == ()
    assert session.commands == ["toggle"], "asked, and touched nothing"


def test_a_switch_the_game_did_not_mention_is_left_alone(
    tmp_path: Path,
) -> None:
    """Not knowing the state is not a reason to guess at it."""
    session = _Session([], toggles="Brief: OFF")
    store = _store_with_maxima(tmp_path)

    changed = asyncio.run(
        Survival(session, store, {}).let_the_game_do_the_work()
    )
    store.close()

    assert changed == ()
    assert session.commands == ["toggle"]
