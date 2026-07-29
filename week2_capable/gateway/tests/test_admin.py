from __future__ import annotations

import pytest

from mud_gateway.admin import FED, SETTABLE, AdminError, AdminSession, refused
from mud_gateway.journal import Journal
from mud_gateway.session import Reply

WHERE = """
Players  Room    Location
Admin    [ 3001] The Temple Of Midgaard
Poucet   [ 3054] Main Street
"""


class ScriptedSession:
    def __init__(self, replies: list[str] | None = None) -> None:
        self.replies = list(replies or [])
        self.lines: list[str] = []
        self.id = "admin-test"

    async def command(self, line: str) -> Reply:
        self.lines.append(line)
        text = self.replies.pop(0) if self.replies else "Ok."
        return Reply(line, text.encode(), b"", True, len(self.lines))

    async def open(self) -> None:
        pass

    async def close(self) -> None:
        pass


@pytest.fixture()
def journal(tmp_path):
    value = Journal(tmp_path / "journal.db")
    yield value
    value.close()


@pytest.fixture()
def admin(journal):
    value = AdminSession(journal, name="admin", password="unused")
    value.session = ScriptedSession()
    return value


async def test_online_and_offline_set_forms_are_not_confused(admin):
    await admin.set_field("poucet", "gold", 500)
    await admin.set_field("poucet", "gold", 0, offline=True)
    assert admin.session.lines == [
        "set poucet gold 500",
        "set file poucet gold 0",
    ]


async def test_unknown_field_is_rejected_before_send(admin):
    with pytest.raises(AdminError, match="not a settable field"):
        await admin.set_field("poucet", "hit", 20)
    assert admin.session.lines == []
    assert "hitpoints" in SETTABLE
    assert FED > 0


async def test_refusal_is_raised_and_journaled(admin, journal):
    admin.session.replies = ["You can't do that."]
    with pytest.raises(AdminError, match="refused"):
        await admin.transfer("nobody")
    event = journal.since("admin-test", kind="admin_operation")[0]
    assert event.payload["refused"] is True


def test_refusal_only_uses_the_first_nonblank_line():
    assert refused("You can't do that.")
    assert not refused(
        "The Temple\nThe walls cracked for some unknown reason."
    )


async def test_locate_reads_immortal_room_ground_truth(admin):
    admin.session.replies = [WHERE]
    assert await admin.locate("poucet") == (3054, "Main Street")


async def test_locate_all_exposes_duplicate_player_sessions(admin):
    admin.session.replies = [
        WHERE + "Poucet   [ 3001] The Temple Of Midgaard\n"
    ]
    assert await admin.locate_all("poucet") == (
        (3054, "Main Street"),
        (3001, "The Temple Of Midgaard"),
    )
