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


def test_week_one_client_completes_handshake_and_discovery(tmp_path):
    env = {
        "GATEWAY_JOURNAL": str(tmp_path / "gateway.db"),
        "GATEWAY_PROFILE": "direct-core",
    }
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
    env = {
        "GATEWAY_JOURNAL": str(tmp_path / "gateway.db"),
        "GATEWAY_PROFILE": "direct-full",
        "GATEWAY_ALLOW": "look,send_raw",
    }
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
