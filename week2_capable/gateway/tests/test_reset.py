from __future__ import annotations

from types import SimpleNamespace

import pytest

from mud_gateway.journal import Journal
from admin_process.reset import (
    DEFAULT_FIELDS,
    ObservedState,
    ResetConflict,
    ResetPlan,
    parse_score,
)
from mud_gateway.session import Reply

SCORE = """You have 20(20) hit, 100(100) mana and 82(82) movement points.
Your armor class is 9/10, and your alignment is 0.
You have 0 exp, 0 gold coins, and 0 questpoints.
This ranks you as Poucet the Swordpupil (level 1).
You are standing.
20H 100M 82V >"""


class FakeAdmin:
    def __init__(self, journal: Journal) -> None:
        self.journal = journal
        self.session = SimpleNamespace(id="admin-test")
        self.calls: list[tuple[object, ...]] = []

    async def goto(self, room: int) -> None:
        self.calls.append(("goto", room))

    async def transfer(self, player: str) -> None:
        self.calls.append(("transfer", player))

    async def restore(self, player: str) -> None:
        self.calls.append(("restore", player))

    async def set_field(self, player: str, field: str, value: int) -> None:
        self.calls.append(("set", player, field, value))

    async def locate_all(self, player: str) -> tuple[tuple[int, str], ...]:
        self.calls.append(("locate_all", player))
        return ((3001, "The Temple Of Midgaard"),)

    async def locate(self, player: str) -> tuple[int, str]:
        self.calls.append(("locate", player))
        return (3001, "The Temple Of Midgaard")


class FakePlayer:
    def __init__(self, journal: Journal) -> None:
        self.journal = journal
        room = SimpleNamespace(
            title="The Temple Of Midgaard",
            exits=("n", "e", "s", "w", "d"),
        )
        self.observations = SimpleNamespace(
            snapshot=lambda: SimpleNamespace(room=room)
        )
        self.commands: list[str] = []
        self.lifecycle: list[str] = []

    async def command(self, line: str) -> Reply:
        self.commands.append(line)
        text = SCORE if line == "score" else "The Temple Of Midgaard"
        return Reply(line, text.encode(), b"", True, 1)

    async def close(self) -> None:
        self.lifecycle.append("close")

    async def open(self) -> None:
        self.lifecycle.append("open")


def test_score_parser_keeps_current_and_maximum():
    state = parse_score(SCORE)
    assert state["hit"] == (20, 20)
    assert state["mana"] == (100, 100)
    assert state["move"] == (82, 82)
    assert state["gold"] == 0
    assert state["hungry"] is False


def test_default_reset_uses_fed_not_starving_values():
    assert DEFAULT_FIELDS["hunger"] > 0
    assert DEFAULT_FIELDS["thirst"] > 0


def test_unread_fields_prevent_vacuous_equality():
    assert "gold" in ObservedState(level=1).unread


async def test_two_resets_produce_identical_mortal_state(tmp_path):
    journal = Journal(tmp_path / "journal.db")
    try:
        admin = FakeAdmin(journal)
        player = FakePlayer(journal)
        plan = ResetPlan()
        first = await plan.apply(admin, player, "poucet")
        second = await plan.apply(admin, player, "poucet")
        assert first.ok
        assert second.ok
        assert first.state.differences(second.state) == {}
        assert player.commands.count("save") == 2
        assert player.lifecycle == ["close", "open", "close", "open"]
        assert first.applied[-2:] == ("save", "reconnect")
        verified = journal.since("admin-test", kind="reset_verified")
        assert len(verified) == 2
        assert all(event.payload["ok"] for event in verified)
    finally:
        journal.close()


def test_verify_detects_drift_and_partial_vitals():
    state = ObservedState(
        level=1,
        hit=(3, 20),
        mana=(100, 100),
        move=(82, 82),
        gold=7,
        exp=0,
        align=0,
        position="standing",
        hungry=False,
        thirsty=False,
        room_title="The Temple Of Midgaard",
        exits=("n",),
    )
    drift = ResetPlan().verify(
        state,
        located=(3001, "The Temple Of Midgaard"),
    )
    assert drift["gold"] == (0, 7)
    assert drift["hit"] == ("full", (3, 20))


def test_verify_rejects_the_wrong_starting_room():
    state = ObservedState(
        level=1,
        hit=(20, 20),
        mana=(100, 100),
        move=(82, 82),
        gold=0,
        exp=0,
        align=0,
        position="standing",
        hungry=False,
        thirsty=False,
        room_title="The Bakery",
        exits=("s",),
    )
    drift = ResetPlan().verify(state, located=(3010, "The Bakery"))
    assert drift["room"] == (3001, 3010)


async def test_reset_rejects_a_concurrent_player_session(tmp_path):
    journal = Journal(tmp_path / "journal.db")
    try:
        admin = FakeAdmin(journal)
        player = FakePlayer(journal)

        async def duplicates(player_name: str) -> tuple[tuple[int, str], ...]:
            admin.calls.append(("locate_all", player_name))
            return (
                (3001, "The Temple Of Midgaard"),
                (3010, "The Bakery"),
            )

        admin.locate_all = duplicates
        with pytest.raises(ResetConflict, match="found 2"):
            await ResetPlan().apply(admin, player, "poucet")
        assert player.commands == []
        assert journal.since("admin-test", kind="reset_rejected")
    finally:
        journal.close()
