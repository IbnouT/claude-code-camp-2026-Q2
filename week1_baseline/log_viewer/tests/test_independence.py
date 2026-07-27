"""The import boundary, asserted so it cannot creep back.

The viewer reads the agent's output and is not part of the agent. That was true of
the code before it was true of the packaging: the two modules imported one symbol
between them, `Config`, purely to find a directory. Everything else shipped alongside
them was dead weight.

A boundary nobody checks is a boundary that closes slowly, one convenient import at a
time, so it is checked here by reading the source rather than by intention. The rule
is deliberately strict: the standard library and this package, nothing else. When the
journey parser is needed for the journey lens it will be a NAMED addition to
`ALLOWED_THIRD_PARTY` with a reason, which is a decision somebody makes rather than a
line somebody adds.
"""

import ast
import sys
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "logviewer"

#: This package's own modules. A relative import stays inside the boundary.
OWN = {"logviewer"}

#: Nothing yet, and the emptiness is the point. Adding a name here is a decision
#: about coupling, made once and visibly, with the reason written beside it.
ALLOWED_THIRD_PARTY: set[str] = set()

#: The agent's package. Named explicitly so the failure message says what went
#: wrong rather than only that something did.
THE_AGENT = "boukensha"


def _imports(path: Path) -> set[str]:
    """Every top-level module name this file imports, relative imports excluded."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # level > 0 is a relative import, which is inside this package.
            if node.level == 0 and node.module:
                found.add(node.module.split(".")[0])
    return found


def _sources() -> list[Path]:
    return sorted(PACKAGE.rglob("*.py"))


class TestTheViewerImportsNothingFromTheAgent(unittest.TestCase):
    def test_there_is_source_to_check(self):
        # A test that silently checks nothing is worse than no test.
        self.assertTrue(_sources(), f"no modules found under {PACKAGE}")

    def test_no_module_reaches_into_the_agent(self):
        offenders = [str(path.relative_to(PACKAGE))
                     for path in _sources() if THE_AGENT in _imports(path)]
        self.assertEqual([], offenders,
                         f"these import {THE_AGENT}: {offenders}")

    def test_every_import_is_the_standard_library_or_this_package(self):
        allowed = set(sys.stdlib_module_names) | OWN | ALLOWED_THIRD_PARTY
        problems = {}
        for path in _sources():
            outside = sorted(_imports(path) - allowed)
            if outside:
                problems[str(path.relative_to(PACKAGE))] = outside
        self.assertEqual({}, problems, f"imports outside the boundary: {problems}")

    def test_the_package_declares_no_dependencies(self):
        # The packaging has to agree with the code, or an install pulls in what
        # the modules were careful not to import.
        text = (PACKAGE.parent / "pyproject.toml").read_text(encoding="utf-8")
        line = next(l for l in text.splitlines()
                    if l.strip().startswith("dependencies"))
        self.assertIn("[]", line, f"dependencies are declared: {line.strip()}")


class TestItRunsWithTheAgentAbsent(unittest.TestCase):
    def test_importing_the_package_does_not_need_the_agent_installed(self):
        """The strongest form of the claim: block the agent, then import.

        Passing because the agent happens to be importable would prove nothing,
        so its name is poisoned in `sys.modules` first. Any import of it, at
        module level or inside a function reached during import, fails loudly.
        """
        saved = {name: module for name, module in sys.modules.items()
                 if name == THE_AGENT or name.startswith(THE_AGENT + ".")}
        for name in saved:
            del sys.modules[name]
        for name in [n for n in sys.modules
                     if n == "logviewer" or n.startswith("logviewer.")]:
            del sys.modules[name]
        sys.modules[THE_AGENT] = None  # any import of it raises ImportError
        try:
            import logviewer

            self.assertTrue(hasattr(logviewer, "read"))
            self.assertTrue(hasattr(logviewer, "list_sessions"))
            self.assertTrue(hasattr(logviewer, "default_dir"))
        finally:
            del sys.modules[THE_AGENT]
            sys.modules.update(saved)


if __name__ == "__main__":
    unittest.main()
