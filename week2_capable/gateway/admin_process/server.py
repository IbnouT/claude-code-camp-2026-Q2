"""Dedicated local-socket process for the typed reset operation."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import stat
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from mud_gateway.admin import AdminSession
from mud_gateway.journal import Journal
from mud_gateway.session import Session

from .reset import ResetPlan


class ResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: str


class AdminServer:
    def __init__(
        self,
        *,
        player: str,
        player_password: str,
        admin_name: str,
        admin_password: str,
        journal_path: Path,
    ) -> None:
        self.player_name = player
        self.player = Session(
            Journal(journal_path),
            name=player,
            password=player_password,
            session_id=f"reset-player-{player}",
        )
        self.admin = AdminSession(
            self.player.journal,
            name=admin_name,
            password=admin_password,
        )

    async def open(self) -> None:
        await self.player.open()
        await self.admin.open()

    async def close(self) -> None:
        await self.admin.close()
        await self.player.close()
        self.player.journal.close()

    async def handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            request = ResetRequest.model_validate_json(await reader.readline())
            if request.operation != "reset":
                raise ValueError("only the reset operation is supported")
            outcome = await ResetPlan().apply(
                self.admin, self.player, self.player_name
            )
            response = {
                "ok": outcome.ok,
                "reset_id": outcome.reset_id,
                "drift": outcome.drift,
                "unread": outcome.state.unread,
            }
        except Exception as error:
            response = {"ok": False, "error": str(error)}
        writer.write((json.dumps(response) + "\n").encode())
        await writer.drain()
        writer.close()
        await writer.wait_closed()


async def serve(socket: Path, server: AdminServer) -> None:
    if socket.exists():
        if not stat.S_ISSOCK(socket.stat().st_mode):
            raise RuntimeError(f"refusing to replace non-socket path {socket}")
        socket.unlink()
    await server.open()
    listener = await asyncio.start_unix_server(server.handle, path=socket)
    os.chmod(socket, 0o600)
    try:
        async with listener:
            await listener.serve_forever()
    finally:
        await server.close()
        socket.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--player", default=os.environ.get("MUD_NAME", "poucet"))
    parser.add_argument("--admin", default=os.environ.get("MUD_ADMIN_NAME", "admin"))
    arguments = parser.parse_args()
    player_password = os.environ.get("MUD_PASSWORD")
    admin_password = os.environ.get("MUD_ADMIN_PASSWORD")
    if not player_password or not admin_password:
        parser.error("MUD_PASSWORD and MUD_ADMIN_PASSWORD are required")
    server = AdminServer(
        player=arguments.player,
        player_password=player_password,
        admin_name=arguments.admin,
        admin_password=admin_password,
        journal_path=arguments.journal,
    )
    asyncio.run(serve(arguments.socket, server))


if __name__ == "__main__":
    main()
