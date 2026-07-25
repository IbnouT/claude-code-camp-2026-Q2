"""The standard tool library (the MCP host): real interop first, then asserted offline.

The headline is real cross-language interop, no LLM and no key: the Ruby
``mud-manager`` daemon (``week0_explore/mud_manager``), an MCP server this step
did not write, auto-booting its own FakeMud, then handshake, tool discovery, and
one real ``look`` call through our host. Step 10's subject is the host layer
underneath the model, so its real run is a real foreign server, not a model
turn. The headline skips cleanly, saying why, only when ruby or the in-repo gem
is absent.

The demo then narrates the host path offline against ``mcp_stub_server.py`` (a
generic protocol-conformance server): spawn, handshake, discover, call over the
wire, register under a prefix, read servers from config, spawn a set at startup,
render the banner line. Deterministic and secret-free.

The guarantees themselves live in ``tests/`` (stdlib unittest, spawning the same
fixture servers), one test per guarantee, run by the step launcher:

    uv run python -m unittest discover -s tests -t .

Behavior verified against the MCP specification 2025-06-18 and this step's plan
(docs/plans/week1_baseline/10_standard_tool_library.md):
- initialize / notifications/initialized / tools/list / tools/call and the
  content-block + isError result shape:
  https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle
  https://modelcontextprotocol.io/specification/2025-06-18/server/tools
- a tool's ``inputSchema.required`` names the required subset; optional
  properties are still listed, with their full schema, but not marked required.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from io import StringIO
from pathlib import Path

import tomllib

from boukensha import __version__ as PKG_VERSION
from boukensha import run_dsl
from boukensha.config import Config
from boukensha.errors import McpError, McpToolCollisionError
from boukensha.mcp import Client
from boukensha.registry import Registry
from boukensha.repl import Repl
from boukensha.tools import mcp as mcp_host

STEP_DIR = Path(__file__).resolve().parents[1]
STUB = str(STEP_DIR / "examples" / "mcp_stub_server.py")
PYPROJECT_VERSION = tomllib.loads((STEP_DIR / "pyproject.toml").read_text())["project"]["version"]

PY = sys.executable

# The instructor's Ruby MCP mud-manager, the headline's real foreign server.
MUD_MANAGER_ROOT = STEP_DIR.parents[2] / "week0_explore" / "mud_manager"
MUD_MANAGER_BIN = MUD_MANAGER_ROOT / "bin" / "mud-manager"
MUD_MANAGER_LIB = MUD_MANAGER_ROOT / "lib"


def spawn_stub(env=None) -> Client:
    """A connected client to a freshly spawned stub server."""
    return Client.spawn(PY, args=[STUB], env=env)


def srv(command, *, args=(), env=None, prefix=None, required=True, timeout=30.0,
        allow=None, deny=()):
    """One ``mcp_servers`` entry, shaped like ``Config.mcp_servers()`` produces."""
    return {"command": command, "args": list(args), "env": dict(env or {}),
            "prefix": prefix, "required": required, "timeout": timeout,
            "allow": allow, "deny": list(deny)}


_FAKE_MUD_SCRIPT = """
$LOAD_PATH.unshift(ARGV[0])
require "mud_manager/fake_mud"
fake = MudManager::FakeMud.new
puts fake.port
STDOUT.flush
STDIN.gets
fake.stop
"""


class FakeMud:
    """The instructor's MudManager::FakeMud in a ruby subprocess, so the Ruby
    mud-manager daemon has an offline MUD to talk to. There is no Python MUD, so
    this is the one place the headline reaches for ruby."""

    def __init__(self, ruby: str):
        self._process = subprocess.Popen(
            [ruby, "-e", _FAKE_MUD_SCRIPT, "--", str(MUD_MANAGER_LIB)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        self.port = int(self._process.stdout.readline().strip())

    def stop(self):
        try:
            self._process.stdin.write("\n")
            self._process.stdin.flush()
        except OSError:
            pass
        self._process.wait()


def _ruby_version_ok(ruby: str) -> bool:
    """True when this ruby binary is >= 3.0, the gem's floor."""
    try:
        out = subprocess.run([ruby, "-e", "print RUBY_VERSION"],
                             capture_output=True, text=True, timeout=10)
        return int(out.stdout.split(".")[0] or 0) >= 3
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False


def find_ruby() -> str | None:
    """The first ruby >= 3.0 we can find, or None.

    PATH first. When PATH only has an old system ruby (macOS ships 2.6), fall
    back to a mise-managed ruby (`mise which ruby`) and then Homebrew, so a
    version-managed install works even in shells where its shims are not active.
    """
    candidates = []
    on_path = shutil.which("ruby")
    if on_path:
        candidates.append(on_path)
    mise = shutil.which("mise")
    if mise:
        try:
            out = subprocess.run([mise, "which", "ruby"],
                                 capture_output=True, text=True, timeout=10)
            if out.returncode == 0 and out.stdout.strip():
                candidates.append(out.stdout.strip())
        except (OSError, subprocess.TimeoutExpired):
            pass
    candidates.append("/opt/homebrew/opt/ruby/bin/ruby")
    for ruby in candidates:
        if Path(ruby).exists() and _ruby_version_ok(ruby):
            return ruby
    return None


def ruby_interop_headline():
    """The headline: a real foreign MCP server through our host, no LLM, no key.

    The Ruby mud-manager daemon is a server this step did not write. It boots
    its own FakeMud, then our host spawns it, handshakes, discovers its tools,
    and dispatches one real ``look``. This is the step's real run: step 10 is
    the host layer underneath the model, so its proof is cross-language
    protocol interop, not a model turn. Skips cleanly, saying why, only when
    ruby or the in-repo gem is absent.
    """
    print("=== boukensha · step 10: the standard tool library (MCP host) ===")
    print()
    ruby = find_ruby() if MUD_MANAGER_BIN.exists() else None
    if ruby is None:
        print("Real-interop headline skipped: needs ruby >= 3.0 (PATH, mise, or")
        print(f"Homebrew) and the week0 mud_manager gem at {MUD_MANAGER_ROOT}.")
        print("The offline block below drives the same host path.")
        print()
        return
    print("Real cross-language interop, no LLM, no key: the Ruby mud-manager")
    print("daemon over our MCP host, against its own FakeMud.")
    fake = None
    try:
        fake = FakeMud(ruby)
        env = {"MUD_HOST": "127.0.0.1", "MUD_PORT": str(fake.port),
               "MUD_NAME": "Gandalf", "MUD_PASSWORD": "secret"}
        # The daemon is stdlib-only and resolves its own $LOAD_PATH, so it is
        # invoked directly: no gem install, no PATH lookup.
        client = Client.spawn(ruby, args=[str(MUD_MANAGER_BIN), "--mcp"],
                              env=env, timeout=15)
        look = client.call_tool("look")
        print(f"  handshake: {(client.server_info or {}).get('name')}   tools: {len(client.tools)}")
        print(f"  look -> {look['text'].strip()[:70]!r}   error={look['error']}")
        client.close()
    except (McpError, OSError, ValueError) as exc:
        print(f"  interop could not complete: {exc}")
    finally:
        if fake:
            fake.stop()
    print()


ruby_interop_headline()


# ==========================================================================
# Demo: the MCP host path, printed the way it would appear live.
# ==========================================================================


def describe_params(spec) -> str:
    """Render a discovered tool's parameters as required/optional, offline."""
    schema = spec.get("inputSchema") or {}
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    if not props:
        return "(none)"
    parts = []
    for name, prop in props.items():
        tag = "required" if name in required else "optional"
        enum = (prop or {}).get("enum")
        extra = f", one of: {', '.join(enum)}" if enum else ""
        parts.append(f"{name} ({tag}{extra})")
    return ", ".join(parts)


def servers_line(summary) -> str:
    """The banner's servers line for a given {name: count} summary."""
    banner = Repl(context=None, registry=None, builder=None, client=None,
                  logger=None, version=PKG_VERSION, servers=summary)._banner()
    return next(ln.strip() for ln in banner.splitlines() if ln.strip().startswith("servers:"))


print("boukensha ships no tools. Every tool the agent can call comes from an MCP")
print("server listed in settings.yaml. The demo below runs the whole host path")
print(f"offline against {Path(STUB).name} (a generic stub MCP server), no network, no key.")
print()
print(f"  package version: {PKG_VERSION}   pyproject version: {PYPROJECT_VERSION}")
print()

# 1. spawn a server and shake hands.
demo_client = spawn_stub()
print("-- 1. spawn a server and handshake -----------------------------------")
print(f"  server_info: {demo_client.server_info}")
print("  protocol:    2025-06-18   clientInfo name: boukensha")
print()

# 2. discover its tools from tools/list.
print("-- 2. discover its tools (tools/list) --------------------------------")
for spec in demo_client.tools:
    print(f"  {spec['name']:<6} params: {describe_params(spec)}")
print()

# 3. call a tool over the wire; a tool-level failure comes back as data.
print("-- 3. call a tool over the wire --------------------------------------")
said = demo_client.call_tool("say", {"message": "hello there", "volume": "shout"})
print(f"  say {{message: 'hello there', volume: 'shout'}}")
print(f"    -> {said['text']!r}   error={said['error']}")
boom = demo_client.call_tool("boom")
print("  boom")
print(f"    -> {boom['text']!r}   error={boom['error']} (returned as data, not raised)")
demo_client.close()
print()

# 4. register the tools into a Registry under a prefix.
print("-- 4. register into a Registry with a prefix -------------------------")
demo_reg = Registry()
prefixed_client = spawn_stub()
mcp_host.register_client(demo_reg, prefixed_client, prefix="tbamud")
print(f"  prefix 'tbamud' -> agent sees: {', '.join(sorted(demo_reg.tools))}")
print(f"  bare 'say' registered? {'say' in demo_reg.tools}")
say_reply = demo_reg.dispatch("tbamud__say", {"message": "hi"})
print(f"  dispatch tbamud__say {{message: 'hi'}}  ->  {say_reply!r}")
print("  the server received the bare name 'say' on the wire (prefix is agent-side)")
prefixed_client.close()
print()

# 5. a capability arrives from config, not code.
print("-- 5. capability from config, not code -------------------------------")
demo_cfg_dir = Path(tempfile.mkdtemp(prefix="boukensha-step10-demo-"))
(demo_cfg_dir / "settings.yaml").write_text(
    "tasks:\n"
    "  player:\n"
    "    provider: anthropic\n"
    "    model: claude-haiku-4-5\n"
    "mcp_servers:\n"
    "  mud:\n"
    "    command: mud-manager\n"
    "    args: [--mcp]\n"
    "    prefix: tbamud\n"
    "    env:\n"
    "      MUD_HOST: localhost\n"
    "      MUD_PORT: 4000\n"          # a YAML integer, stringified for the spawn env
    "  opt:\n"
    "    command: other\n"
    "    required: false\n"
)
# Point Config at the demo dir, restoring the caller's env even on a raise so
# a failure here can never leak a temp BOUKENSHA_DIR into what follows.
_demo_prev_dir = os.environ.get("BOUKENSHA_DIR")
os.environ["BOUKENSHA_DIR"] = str(demo_cfg_dir)
try:
    demo_servers = Config().mcp_servers()
finally:
    if _demo_prev_dir is None:
        os.environ.pop("BOUKENSHA_DIR", None)
    else:
        os.environ["BOUKENSHA_DIR"] = _demo_prev_dir
for name, entry in demo_servers.items():
    print(f"  {name}: {entry}")
print()

# 6. startup wiring: spawn the configured servers, honor required/optional.
print("-- 6. startup wiring -------------------------------------------------")
up = run_dsl._register_mcp_servers(Registry(), {
    "north": srv(PY, args=[STUB], prefix="n"),
    "south": srv(PY, args=[STUB], prefix="s"),
})
print(f"  two servers spawned in order -> {up}")
warn = StringIO()
opt = run_dsl._register_mcp_servers(Registry(), {
    "ghost": srv("no_such_command_xyz", required=False),
}, err=warn)
print(f"  optional server that can't spawn -> summary {opt}, warning:")
print(f"    {warn.getvalue().strip()}")
try:
    run_dsl._register_mcp_servers(Registry(), {
        "a": srv(PY, args=[STUB]),
        "b": srv(PY, args=[STUB], required=False),
    })
except McpToolCollisionError as exc:
    print(f"  name collision (fatal even for an optional server) -> {exc}")
print()

# 7. the banner line that tells a user what the agent can actually do.
print("-- 7. the REPL banner's servers line ---------------------------------")
print(f"  {servers_line({'mud': 2, 'fs': 11})}")
print(f"  {servers_line({})}")
print()

print("Every guarantee behind this demo is pinned by the test suite:")
print("  uv run python -m unittest discover -s tests -t .")
print("34 tests over the client, transport, host layer, config, and wiring.")
