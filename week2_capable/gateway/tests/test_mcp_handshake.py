"""The Week 1 hand-written client can discover the profiled gateway."""

from __future__ import annotations

import json
import pathlib
import sys
import types

AGENT_PROJECT = pathlib.Path(__file__).resolve().parents[2] / "agent"
AGENT_PACKAGE = AGENT_PROJECT / "boukensha"

# Load the hand-written client without importing the agent application's
# package initializer and its unrelated runtime dependencies.
boukensha = types.ModuleType("boukensha")
boukensha.__path__ = [str(AGENT_PACKAGE)]
sys.modules.setdefault("boukensha", boukensha)
mcp_package = types.ModuleType("boukensha.mcp")
mcp_package.__path__ = [str(AGENT_PACKAGE / "mcp")]
sys.modules.setdefault("boukensha.mcp", mcp_package)

from boukensha.mcp.client import Client  # noqa: E402


def gateway_env(tmp_path, surface: str) -> dict[str, str]:
    directory = tmp_path / ".boukensha"
    directory.mkdir()
    (directory / "settings.yaml").write_text(
        "gateway:\n"
        f"  journal: {tmp_path / 'gateway.db'}\n"
        "  surface:\n"
        f"{surface}",
        encoding="utf-8",
    )
    return {"BOUKENSHA_DIR": str(directory)}


def test_week_one_client_completes_handshake_and_discovery(tmp_path):
    env = gateway_env(tmp_path, "    profile: direct-core\n")
    client = Client.spawn(
        sys.executable,
        args=["-m", "mud_gateway.mcp_server"],
        env=env,
        timeout=10,
    )
    try:
        assert client.server_info["name"] == "torii"
        names = {tool["name"] for tool in client.tools}
        assert {"move", "look", "attack", "poll"} <= names
        assert "send_raw" not in names
        denied = client.call_tool("cast_spell", {"spell": "armor"})
        payload = json.loads(denied["text"])
        assert denied["error"]
        assert payload["code"] == "permission_denied"
    finally:
        client.close()


def test_configured_raw_profile_is_visible_to_the_same_client(tmp_path):
    env = gateway_env(
        tmp_path,
        "    profile: direct-full\n"
        "    disable: [attack, cast_spell, channel_say, check, consider, "
        "consume_item, drop_item, equip_item, examine, flee, get_item, move, "
        "mud_status, poll, practice, put_item, save_character, say, "
        "set_position, shop, skill_strike, tell, track, use_magic_item]\n"
        "    allow_raw: true\n",
    )
    client = Client.spawn(
        sys.executable,
        args=["-m", "mud_gateway.mcp_server"],
        env=env,
        timeout=10,
    )
    try:
        assert {tool["name"] for tool in client.tools} == {"look", "send_raw"}
    finally:
        client.close()
