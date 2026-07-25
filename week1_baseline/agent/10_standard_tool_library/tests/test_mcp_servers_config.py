"""``mcp_servers:`` config, the startup wiring, the banner, and the version."""

import tomllib
from io import StringIO

from boukensha import __version__ as PKG_VERSION
from boukensha import run_dsl
from boukensha.config import Config
from boukensha.errors import ConfigError, McpServerError, McpToolCollisionError
from boukensha.registry import Registry
from boukensha.repl import Repl

from .helper import PY, STEP_DIR, STUB, McpTestCase, config_from, srv

TASKS = "tasks:\n  player:\n    provider: anthropic\n    model: claude-haiku-4-5\n"


class TestMcpServersConfig(McpTestCase):
    def test_parses_entries_stringifies_env_and_applies_defaults(self):
        with config_from(
            TASKS
            + "mcp_servers:\n"
            + "  mud:\n    command: mud-manager\n    args: [--mcp]\n"
            + "    prefix: tbamud\n"
            + "    env:\n      MUD_HOST: localhost\n      MUD_PORT: 4000\n"
            + "  opt:\n    command: other\n    required: false\n"
            + "  bare: {}\n"
        ):
            servers = Config().mcp_servers()
        self.assertEqual(
            {"command": "mud-manager", "args": ["--mcp"],
             "env": {"MUD_HOST": "localhost", "MUD_PORT": "4000"},
             "prefix": "tbamud", "required": True, "timeout": 30.0,
             "allow": None, "deny": []},
            servers["mud"])
        self.assertEqual(
            {"command": "", "args": [], "env": {}, "prefix": None,
             "required": True, "timeout": 30.0, "allow": None, "deny": []},
            servers["bare"])
        self.assertFalse(servers["opt"]["required"])

    def test_an_absent_block_yields_empty(self):
        with config_from(TASKS):
            self.assertEqual({}, Config().mcp_servers())

    def test_each_server_gets_a_per_call_timeout(self):
        with config_from(
            TASKS + "mcp_servers:\n"
            + "  quick:\n    command: x\n    timeout: 5\n"
            + "  slow:\n    command: y\n"
        ):
            servers = Config().mcp_servers()
        self.assertEqual(5.0, servers["quick"]["timeout"])
        self.assertEqual(30.0, servers["slow"]["timeout"])

    def test_a_malformed_entry_is_rejected_at_load_naming_the_field(self):
        for bad in ("mcp_servers:\n  s:\n    command: x\n    args: not-a-list\n",
                    "mcp_servers:\n  s:\n    command: x\n    env: [a, b]\n"):
            with config_from(TASKS + bad):
                with self.assertRaises(ConfigError):
                    Config()


class TestStartupWiring(McpTestCase):
    def test_a_required_server_that_fails_to_spawn_raises_naming_it(self):
        with self.assertRaises(McpServerError) as ctx:
            run_dsl._register_mcp_servers(
                Registry(), {"badmud": srv("no_such_command_xyz")})
        self.assertIn("badmud", str(ctx.exception))

    def test_an_optional_server_that_fails_to_spawn_warns_and_continues(self):
        err = StringIO()
        summary = run_dsl._register_mcp_servers(
            Registry(), {"badmud": srv("no_such_command_xyz", required=False)},
            err=err)
        self.assertEqual({}, summary)
        self.assertIn("badmud", err.getvalue())
        self.assertIn("optional", err.getvalue())

    def test_required_false_does_not_excuse_a_collision(self):
        with self.assertRaises(McpToolCollisionError):
            run_dsl._register_mcp_servers(Registry(), {
                "first": srv(PY, args=[STUB]),
                "second": srv(PY, args=[STUB], required=False),
            })

    def test_the_helper_returns_a_tool_count_per_server(self):
        summary = run_dsl._register_mcp_servers(
            Registry(), {"mud": srv(PY, args=[STUB])})
        self.assertEqual({"mud": 2}, summary)


class TestBannerAndVersion(McpTestCase):
    @staticmethod
    def _banner(servers):
        return Repl(context=None, registry=None, builder=None, client=None,
                    logger=None, version=PKG_VERSION, servers=servers)._banner()

    def test_the_banner_shows_the_servers_line(self):
        banner = self._banner({"mud": 2, "fs": 11})
        self.assertIn("servers:", banner)
        self.assertIn("mud (2)", banner)
        self.assertIn("fs (11)", banner)
        self.assertIn("none", self._banner({}))

    def test_version_matches_pyproject(self):
        pyproject = tomllib.loads(
            (STEP_DIR / "pyproject.toml").read_text())["project"]["version"]
        self.assertEqual("0.10.0", PKG_VERSION)
        self.assertEqual("0.10.0", pyproject)
