from __future__ import annotations

import ast
from pathlib import Path

from mud_gateway.commands import IMMORTAL
from mud_gateway.profiles import PROFILES, Surface

PACKAGE = Path(__file__).resolve().parents[1] / "mud_gateway"
# The mortal runtime is the WHOLE package except admin.py, which holds the typed
# immortal operations and is imported only by the separate admin_process. Scanning
# the package dynamically means a future mortal module cannot quietly reach admin
# code without this invariant catching it.
MORTAL_MODULES = tuple(sorted(p.name for p in PACKAGE.glob("*.py") if p.name != "admin.py"))
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
