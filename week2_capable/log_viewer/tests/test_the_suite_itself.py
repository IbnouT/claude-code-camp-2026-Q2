"""The suite's own shape, because a test file can lie about how much it ran.

`if __name__ == "__main__": unittest.main()` collects what is DEFINED when it runs, and a
module body runs top to bottom. A class added below that line is invisible to it. The
file still passes, reports a number, and says OK, so the person who runs one file while
working on it gets a green result that skipped the part they were editing.

It arrived from appending classes to the end of files that already had a footer. Across
this project it left 116 tests in 11 files unreachable that way, and the full-suite run
stayed honest the whole time because discovery imports a module rather than executing it
as `__main__`. That is what makes it worth a test rather than a memory: nothing failed.

Checked here rather than in every suite because this package has the most test files and
the check reads any directory it is pointed at.
"""

import ast
import unittest
from pathlib import Path

#: This package's tests, and the agent steps beside it. A check that only guarded its own
#: directory would have missed the four agent files where the same thing happened.
ROOTS = [
    Path(__file__).resolve().parent,
    Path(__file__).resolve().parents[2] / "agent" / "tests",
]


def _files():
    for root in ROOTS:
        if root.is_dir():
            yield from sorted(root.glob("test_*.py"))


def _guard_line(source: str) -> int | None:
    """The line of the last `if __name__ == "__main__"`, or None."""
    lines = [i for i, l in enumerate(source.splitlines(), start=1)
             if l.startswith("if __name__ ==")]
    return lines[-1] if lines else None


class TestNoTestHidesBelowTheMainGuard(unittest.TestCase):
    def test_there_are_files_to_check(self):
        # A structural test over an empty set passes and means nothing, which is the
        # failure mode of every check in this file's own category. So every root that
        # exists must contribute at least one file, which catches a mis-rooted scan
        # without pinning a magic total that a consolidated layout would break.
        present = [r for r in ROOTS if r.is_dir()]
        self.assertTrue(present, "no configured test root exists")
        for root in present:
            self.assertTrue(list(root.glob("test_*.py")),
                            f"no test files found under {root}")
        files = list(_files())
        self.assertGreater(len(files), 10, f"only found {len(files)} test files")

    def test_no_class_is_defined_after_the_guard(self):
        problems = {}
        for path in _files():
            source = path.read_text(encoding="utf-8")
            guard = _guard_line(source)
            if guard is None:
                continue
            hidden = [node.name for node in ast.walk(ast.parse(source))
                      if isinstance(node, ast.ClassDef) and node.lineno > guard]
            if hidden:
                problems[str(path.name)] = hidden
        self.assertEqual({}, problems,
                         "these classes are invisible to unittest.main(), so running "
                         f"the file directly skips them: {problems}")

    def test_no_test_function_is_defined_after_the_guard_either(self):
        # A bare test function outside a class is rarer and hides the same way.
        problems = {}
        for path in _files():
            source = path.read_text(encoding="utf-8")
            guard = _guard_line(source)
            if guard is None:
                continue
            tree = ast.parse(source)
            hidden = [n.name for n in tree.body
                      if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                      and n.name.startswith("test") and n.lineno > guard]
            if hidden:
                problems[path.name] = hidden
        self.assertEqual({}, problems, f"functions below the guard: {problems}")

    def test_the_guard_is_the_last_statement_where_it_appears(self):
        """Nothing at all after it, so the next append lands above rather than below.

        The class check catches the damage. This catches the shape that causes it, which
        is the difference between finding this bug again and not having it.
        """
        problems = []
        for path in _files():
            source = path.read_text(encoding="utf-8")
            guard = _guard_line(source)
            if guard is None:
                continue
            tree = ast.parse(source)
            after = [n for n in tree.body
                     if n.lineno > guard and not isinstance(n, ast.If)]
            if after:
                problems.append(f"{path.name}:{after[0].lineno}")
        self.assertEqual([], problems,
                         f"statements after the main guard: {problems}")


if __name__ == "__main__":
    unittest.main()
