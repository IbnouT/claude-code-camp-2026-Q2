"""The MCP client and transport: handshake, calls, and every failure mode."""

import tempfile
from pathlib import Path

from boukensha.errors import McpError, McpTimeoutError
from boukensha.mcp import Client, StdioTransport

from .helper import MUD_SERVER, PY, STUB, McpTestCase, spawn_stub


class TestClient(McpTestCase):
    def test_handshake_exposes_server_info(self):
        client = self.track(spawn_stub())
        self.assertEqual({"name": "stub-mud", "version": "0.1.0"}, client.server_info)

    def test_tools_are_discovered_from_tools_list(self):
        client = self.track(spawn_stub())
        self.assertEqual({"say", "boom"}, {t["name"] for t in client.tools})

    def test_call_tool_reaches_the_server(self):
        client = self.track(spawn_stub())
        said = client.call_tool("say", {"message": "hello"})
        self.assertFalse(said["error"])
        self.assertIn("you say: hello", said["text"])

    def test_tool_level_failure_is_data_not_an_exception(self):
        client = self.track(spawn_stub())
        boom = client.call_tool("boom")
        self.assertTrue(boom["error"])
        self.assertEqual("kaboom", boom["text"])

    def test_nonexistent_command_raises_at_spawn(self):
        with self.assertRaises(FileNotFoundError):
            Client.spawn("no_such_command_boukensha_xyz")

    def test_json_rpc_error_on_handshake_raises(self):
        # Not a silently empty client: a rejected initialize is an error.
        with self.assertRaises(McpError) as ctx:
            Client.spawn(PY, args=[STUB], env={"STUB_INIT_ERROR": "1"})
        self.assertIn("initialize", str(ctx.exception))

    def test_timeout_raises_and_leaves_the_connection_open(self):
        client = self.track(spawn_stub(env={"STUB_SLEEP_SECONDS": "1"}, timeout=0.3))
        with self.assertRaises(McpTimeoutError):
            client.call_tool("nap")
        self.assertFalse(client.closed)

    def test_crash_names_the_exit_code_and_closes_a_non_respawning_client(self):
        # An injected transport has no respawn factory, so the crash is final.
        transport = StdioTransport(PY, args=[STUB], env={"STUB_CRASH_ON": "boom"})
        client = self.track(Client(transport))
        with self.assertRaises(McpError) as ctx:
            client.call_tool("boom")
        self.assertIn("exit code", str(ctx.exception))
        self.assertTrue(client.closed)

    def test_non_text_content_renders_as_a_described_placeholder(self):
        client = self.track(spawn_stub(env={"STUB_NONTEXT": "1"}))
        pic = client.call_tool("picture")
        self.assertEqual("[image: image/png]", pic["text"])
        self.assertFalse(pic["error"])


class TestRespawn(McpTestCase):
    def test_a_crashed_server_is_respawned_and_the_call_recovers(self):
        marker = Path(tempfile.mkdtemp(prefix="boukensha-respawn-")) / "crashed"
        client = self.track(spawn_stub(env={"STUB_CRASH_ONCE": str(marker)},
                                       sleep=lambda _s: None))
        said = client.call_tool("say", {"message": "alive"})
        self.assertIn("you say: alive", said["text"])
        self.assertFalse(client.closed)

    def test_a_server_crashing_every_call_hits_the_cap_then_fails(self):
        # Never an infinite loop or a hang: the error surfaces to the agent.
        client = self.track(spawn_stub(env={"STUB_CRASH_ON": "say"},
                                       sleep=lambda _s: None))
        with self.assertRaises(McpError):
            client.call_tool("say", {"message": "x"})
        self.assertTrue(client.closed)


class TestDomainServer(McpTestCase):
    def test_the_mud_fixture_round_trips_through_the_host(self):
        # A domain-shaped server, not only the generic protocol stub. The real
        # Ruby daemon gets the same treatment in the example's headline.
        client = self.track(Client.spawn(PY, args=[MUD_SERVER]))
        self.assertEqual({"look", "move"}, {t["name"] for t in client.tools})
        look = client.call_tool("look")
        self.assertIn("clearing", look["text"].lower())
        self.assertFalse(look["error"])
        move = client.call_tool("move", {"direction": "north"})
        self.assertIn("grove", move["text"].lower())
