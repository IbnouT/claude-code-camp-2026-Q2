from __future__ import annotations

import ast
from pathlib import Path

from mud_gateway.commands import IMMORTAL
from mud_gateway.profiles import PROFILES, Surface

PACKAGE = Path(__file__).resolve().parents[1] / "mud_gateway"
# What has to hold is that the agent cannot reach immortal powers, and that
# nothing immortal reaches the agent. Which module imports what is a stand-in
# for the first, and a useful one: a module that cannot see admin code cannot
# expose it. Two modules are excused and named, because they exist to use an
# immortal connection on the harness's behalf and never on the agent's.
#
#   admin.py    the typed immortal operations themselves
#   observer.py reads the room number the game states, and asks nothing else
#
# The second half, that no immortal value reaches the agent, is not an import
# question at all, and is asserted below over the payloads themselves.
EXCUSED = {"admin.py", "observer.py"}
MORTAL_MODULES = tuple(sorted(
    str(path.relative_to(PACKAGE))
    for path in PACKAGE.rglob("*.py")
    if path.name not in EXCUSED
))
FORBIDDEN_LEAVES = {"admin", "admin_server", "reset"}
FORBIDDEN_ROOTS = {"admin_process"}


def _imported_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return names


def test_mortal_runtime_does_not_import_admin_code():
    assert MORTAL_MODULES, "expected mortal modules to scan"
    for name in MORTAL_MODULES:
        for imported in _imported_modules((PACKAGE / name).read_text()):
            parts = imported.split(".")
            assert not FORBIDDEN_ROOTS & set(parts), (name, imported)
            assert parts[-1] not in FORBIDDEN_LEAVES, (name, imported)


def test_default_mortal_surface_remains_admin_free():
    names = {schema["name"] for schema in Surface(PROFILES["direct-full"]).schemas()}
    assert len(names) == 25
    assert not names & IMMORTAL
    assert not {"reset", "admin", "goto", "restore", "transfer"} & names
