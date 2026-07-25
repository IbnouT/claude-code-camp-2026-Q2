"""The global-executable loader: resolve an implementation and a config
directory, then boot the REPL.

The installed console script ``boukensha`` (declared in ``pyproject.toml`` under
``[project.scripts]``) targets :func:`main` here. ``main`` is a thin wrapper: it
calls :func:`load_and_start_repl`, which decides which step folder to run and
which config directory it should read, then starts the interactive session.

Two settings are resolved independently, each in the same three-tier order:

    1. an environment variable (``BOUKENSHA_PATH`` / ``BOUKENSHA_DIR``)
    2. a key in ``~/.boukensharc`` (``boukensha_path`` / ``boukensha_dir``)
    3. a default (the installed package / ``Config``'s own resolution)

An explicit environment variable always wins over the rc file. This mirrors the
reference gem's ``BoukenshaLoader`` while adapting the file-path ``require`` to
Python's import-by-name model: a resolved step folder is put at the front of
``sys.path`` and the cached ``boukensha`` module dropped, so the step's own
package shadows the installed one on a fresh import.
"""

from __future__ import annotations

import importlib
import os
import sys
from typing import Any, Callable, NoReturn, TextIO

import yaml


def rc_file() -> str:
    """Absolute path to ``~/.boukensharc`` (respects the current ``HOME``)."""
    return os.path.expanduser("~/.boukensharc")


def _abort(message: str, err: TextIO) -> NoReturn:
    """Write a diagnostic to stderr and exit 1, Ruby ``abort`` semantics.

    Typed ``NoReturn`` because it always raises, so callers can rely on it to
    short-circuit and a type checker can verify ``resolve()``'s return type.
    """
    print(message, file=err)
    raise SystemExit(1)


def load_rc(*, err: TextIO = sys.stderr) -> dict:
    """Parse ``~/.boukensharc`` into a mapping.

    A YAML mapping is returned as-is. A bare string is the legacy single-path
    format and becomes ``{"boukensha_path": <string>}``. An empty or absent file
    means no settings (``{}``). Any other shape, or invalid YAML, aborts naming
    the file and the expected shape.
    """
    path = rc_file()
    if not os.path.exists(path):
        return {}

    with open(path, "r", encoding="utf-8") as handle:
        text = handle.read()

    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        _abort(f"boukensha: invalid YAML in {path}: {exc}", err)

    if isinstance(parsed, dict):
        unknown = set(parsed) - {"boukensha_path", "boukensha_dir"}
        if unknown:
            _abort(f"boukensha: unknown key(s) in {path}: "
                   f"{', '.join(sorted(map(str, unknown)))}. "
                   f"Allowed: boukensha_path, boukensha_dir.", err)
        return parsed
    if isinstance(parsed, str):
        return {"boukensha_path": parsed}
    if parsed is None:
        return {}
    _abort(f"boukensha: {path} must contain a YAML mapping "
           f"(boukensha_path and/or boukensha_dir) or a bare path string", err)


def _expand(path: str, base: str) -> str:
    """Expand ``path`` like Ruby ``File.expand_path(path, base)``.

    A leading ``~`` expands to the home directory. A relative path is joined
    onto ``base``. The result is normalized and absolute (``base`` is absolute
    at every call site).
    """
    expanded = os.path.expanduser(path)
    if not os.path.isabs(expanded):
        expanded = os.path.join(base, expanded)
    return os.path.normpath(expanded)


def expand_rc_path(value: Any) -> str | None:
    """Expand an rc-file path value relative to the home directory.

    ``None``, a non-string, or an empty/whitespace string yields ``None``.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    return _expand(value, os.path.dirname(rc_file()))


def resolve(*, err: TextIO = sys.stderr) -> str | None:
    """Resolve the implementation directory and apply the config-dir side effect.

    Returns the step directory to load, or ``None`` for the bundled (installed)
    package. As a side effect, sets ``BOUKENSHA_DIR`` from the rc file when the
    environment variable is unset, before any implementation loads, so ``Config``
    inside the loaded step reads it.
    """
    rc = load_rc(err=err)

    rc_config_dir = expand_rc_path(rc.get("boukensha_dir"))
    if not os.environ.get("BOUKENSHA_DIR") and rc_config_dir:
        os.environ["BOUKENSHA_DIR"] = rc_config_dir

    env_path = os.environ.get("BOUKENSHA_PATH")
    if env_path:
        source, origin = env_path, "the BOUKENSHA_PATH environment variable"
    else:
        rc_path = expand_rc_path(rc.get("boukensha_path"))
        if not rc_path:
            return None
        source, origin = rc_path, f"boukensha_path in {rc_file()}"

    step_dir = _expand(source, os.getcwd())
    if os.path.exists(os.path.join(step_dir, "boukensha", "__init__.py")):
        return step_dir

    # Name the source that produced the bad path, so the user knows which knob
    # to turn rather than being told to check both.
    _abort(
        "boukensha: no boukensha/__init__.py found at:\n"
        f"       {step_dir}\n"
        f"       (set via {origin})",
        err,
    )


def _import_impl(step_dir: str | None) -> Any:
    """Import the ``boukensha`` implementation to run.

    Bundled (``step_dir`` is ``None``): import the installed package by name.
    A step folder: put it at the front of ``sys.path`` and drop any cached
    ``boukensha`` module tree, so a fresh import binds the step's own package.
    """
    if step_dir is None:
        return importlib.import_module("boukensha")

    # Invariant: nothing from the installed ``boukensha`` package may be
    # instantiated before this eviction completes. The running frame holds its
    # own functions by direct reference, so evicting the module dict is safe,
    # but an installed-package object built earlier would carry stale class
    # identity against the freshly shadow-imported package.
    sys.path.insert(0, step_dir)
    for name in [n for n in sys.modules if n == "boukensha" or n.startswith("boukensha.")]:
        del sys.modules[name]
    return importlib.import_module("boukensha")


def _default_runner(module: Any) -> None:
    """The real boot: call the loaded implementation's ``repl``."""
    module.repl()


def load_and_start_repl(
    *,
    repl_runner: Callable[[Any], None] | None = None,
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> None:
    """Resolve, import, guard, and start the REPL.

    ``repl_runner`` and the output streams are injection seams: the default
    runner calls ``module.repl()`` (interactive, live), and tests pass a stub
    runner plus captured streams to drive the boot path offline. The resolution
    and guard behavior is identical on both paths.
    """
    out = out if out is not None else sys.stdout
    err = err if err is not None else sys.stderr
    runner = repl_runner if repl_runner is not None else _default_runner

    step_dir = resolve(err=err)
    module = _import_impl(step_dir)

    if os.environ.get("BOUKENSHA_DEBUG"):
        location = step_dir if step_dir else os.path.dirname(os.path.dirname(module.__file__))
        print(f"[boukensha] loading from: {location}", file=err)

    if not hasattr(module, "repl"):
        where = step_dir if step_dir else "the bundled package"
        _abort(
            f"boukensha: the step at {where}\n"
            "       does not support the interactive REPL (added in step 08).\n"
            "       Run its examples directly, e.g.:\n"
            f"         uv run {step_dir}/examples/example.py\n"
            "       Or point BOUKENSHA_PATH at step 08 or later.",
            err,
        )

    try:
        runner(module)
    except KeyboardInterrupt:
        print("Interrupted.", file=out)


def main() -> None:
    """Console-script entry point: handle top-level flags, then boot the REPL.

    ``--version`` and ``--help`` are answered by the loader itself before any
    step resolves, so ``boukensha --version`` reports the installed command's
    version rather than launching a REPL. Unknown flags are rejected loudly by
    argparse instead of being forwarded to the REPL as a first line.
    """
    import argparse

    from . import __version__

    parser = argparse.ArgumentParser(
        prog="boukensha",
        description="Boot the boukensha MUD agent for the resolved step.",
    )
    parser.add_argument(
        "--version", action="version", version=f"boukensha {__version__}")
    parser.parse_args()
    load_and_start_repl()
