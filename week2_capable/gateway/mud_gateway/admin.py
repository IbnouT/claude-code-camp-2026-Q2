"""Typed privileged operations for the separate admin process."""

from __future__ import annotations

import re

from .journal import Journal
from .session import Session

TEMPLE = 3001
FED = 24
SETTABLE = frozenset({
    "ac", "afk", "age", "align", "bank", "brief", "cha", "class", "color",
    "con", "damroll", "deleted", "dex", "drunk", "exp", "frozen", "gold",
    "height", "hitpoints", "hunger", "int", "invis", "invstart", "killer",
    "level", "loadroom", "mana", "maxhit", "maxmana", "maxmove", "move",
    "name", "nodelete", "nohassle", "nosummon", "nowizlist", "olc",
    "password", "poofout", "practices", "quest", "questhistory",
    "questpoints", "room", "screenwidth", "sex", "showvnums", "siteok",
    "str", "stradd", "thief", "thirst", "title", "variable", "weight", "wis",
})
WHERE_LINE = re.compile(r"^(\w+)\s+\[\s*(\d+)\]\s+(.+?)(?:\s{2,}|$)", re.M)
REFUSAL = re.compile(r"^(invalid\b|you can't\b|you cannot\b|no such\b|huh\?|sorry\b)", re.I)


def refused(text: str) -> bool:
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return bool(REFUSAL.search(first))


class AdminError(Exception):
    pass


class AdminSession:
    """An immortal connection available only to the admin process."""

    def __init__(
        self,
        journal: Journal,
        *,
        name: str,
        password: str,
        host: str = "127.0.0.1",
        port: int = 4000,
    ) -> None:
        self.session = Session(
            journal,
            name=name,
            password=password,
            host=host,
            port=port,
            session_id=f"admin-{name}",
        )
        self.journal = journal

    async def open(self) -> None:
        await self.session.open()

    async def close(self) -> None:
        await self.session.close()

    async def _run(self, line: str, operation: str) -> str:
        reply = await self.session.command(line)
        declined = refused(reply.text)
        self.journal.append(
            self.session.id,
            "admin_operation",
            {
                "operation": operation,
                "line": line,
                "refused": declined,
                "reply_seq": reply.seq,
            },
        )
        if declined:
            preview = " ".join(reply.text.split())[:100]
            raise AdminError(f"{operation} refused: {preview}")
        return reply.text

    async def goto(self, room: int) -> str:
        return await self._run(f"goto {room}", "goto")

    async def transfer(self, player: str) -> str:
        return await self._run(f"trans {player}", "transfer")

    async def restore(self, player: str) -> str:
        return await self._run(f"restore {player}", "restore")

    async def set_field(
        self, player: str, field: str, value: object, *, offline: bool = False
    ) -> str:
        if field not in SETTABLE:
            raise AdminError(f"{field!r} is not a settable field")
        form = "set file" if offline else "set"
        return await self._run(f"{form} {player} {field} {value}", f"set:{field}")

    async def locate_all(self, player: str) -> tuple[tuple[int, str], ...]:
        text = await self._run("where", "locate")
        return tuple(
            (int(match.group(2)), match.group(3).strip())
            for match in WHERE_LINE.finditer(text)
            if match.group(1).casefold() == player.casefold()
        )

    async def locate(self, player: str) -> tuple[int, str] | None:
        matches = await self.locate_all(player)
        return matches[0] if matches else None
