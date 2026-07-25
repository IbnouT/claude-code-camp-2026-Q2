"""Shared fixtures for the step-10 MCP test suite.

The tests spawn real subprocess servers (the fixtures in ``examples/``), so
every guarantee is proven end to end over stdio, not against in-process fakes.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

STEP_DIR = Path(__file__).resolve().parents[1]
STUB = str(STEP_DIR / "examples" / "mcp_stub_server.py")
MUD_SERVER = str(STEP_DIR / "examples" / "mcp_mud_server.py")
PY = sys.executable

sys.path.insert(0, str(STEP_DIR))

from boukensha.mcp import Client  # noqa: E402


def spawn_stub(env=None, **kwargs) -> Client:
    """A connected client to a freshly spawned stub server."""
    return Client.spawn(PY, args=[STUB], env=env, **kwargs)


def srv(command, *, args=(), env=None, prefix=None, required=True, timeout=30.0,
        allow=None, deny=()):
    """One ``mcp_servers`` entry, shaped like ``Config.mcp_servers()`` produces."""
    return {"command": command, "args": list(args), "env": dict(env or {}),
            "prefix": prefix, "required": required, "timeout": timeout,
            "allow": allow, "deny": list(deny)}


@contextmanager
def config_from(yaml_text: str):
    """A ``Config`` loaded from a temporary ``BOUKENSHA_DIR`` holding this yaml."""
    cfg_dir = Path(tempfile.mkdtemp(prefix="boukensha-step10-test-"))
    (cfg_dir / "settings.yaml").write_text(yaml_text)
    prev = os.environ.get("BOUKENSHA_DIR")
    os.environ["BOUKENSHA_DIR"] = str(cfg_dir)
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop("BOUKENSHA_DIR", None)
        else:
            os.environ["BOUKENSHA_DIR"] = prev


class McpTestCase(unittest.TestCase):
    """Closes every client registered with ``track`` on teardown."""

    def setUp(self):
        self._clients = []

    def tearDown(self):
        for client in self._clients:
            try:
                client.close()
            except Exception:
                pass

    def track(self, client):
        self._clients.append(client)
        return client
