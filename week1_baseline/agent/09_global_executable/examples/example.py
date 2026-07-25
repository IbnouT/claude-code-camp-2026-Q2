"""The global-executable loader: the real command booting live, then asserted offline.

The headline is the installed ``boukensha`` command's own path: with
``BOUKENSHA_LIVE=1`` the loader resolves this step, shadow-imports it, and boots
one live REPL turn against the configured provider. Gated off, the suite stays
offline and drives the same loader through every scenario the command hits: an rc
file that names a step, an env var that overrides it, the bundled default, a boot
that dispatches to a step's ``repl``, a step that predates the REPL, the
``BOUKENSHA_DEBUG`` line, and the rc error messages. Every abort and debug line
printed is the loader's real output, captured from a stream.

The offline block needs no network and no API key. Resolution and rc parsing are
pure functions of ``HOME``, the loader environment variables, and the current
directory, so each scenario pins a temporary ``HOME`` with a crafted
``~/.boukensharc`` and step-shaped directories. The boot path ends in the
interactive, live ``repl()``, so ``load_and_start_repl`` takes an injected
``repl_runner`` and output streams. One assertion boots this step's *real*
package through the loader against a stub transport, proving the shadowed module
works (a different object, config crossing the boundary, a completed turn), not
merely that dispatch fired.

Behavior verified against the reference gem's ``BoukenshaLoader`` and this step's
plan (docs/plans/week1_baseline/09_global_executable.md):
- rc-file path values expand relative to the home directory; an env
  ``BOUKENSHA_PATH`` expands relative to the current directory.
- an explicit environment variable always wins over the rc file.
- ``BOUKENSHA_DIR`` from the rc file is applied only when the env var is unset.
- a bare-string rc is the legacy single-path format, equal to ``boukensha_path``.
- ``yaml.safe_load`` parses the rc, constructing no arbitrary Python objects
  (https://pyyaml.org/wiki/PyYAMLDocumentation, "Loading YAML" / safe_load).
"""

import io
import json
import os
import sys
import tempfile
import tomllib
from pathlib import Path

# Read the package version and pyproject version before any boot test replaces
# the cached ``boukensha`` module in ``sys.modules``.
from boukensha import __version__ as PKG_VERSION  # noqa: E402
from boukensha.loader import load_and_start_repl, main, resolve  # noqa: E402

STEP_DIR = Path(__file__).resolve().parents[1]
PYPROJECT_VERSION = tomllib.loads((STEP_DIR / "pyproject.toml").read_text())["project"]["version"]

REAL_BOUKENSHA = sys.modules["boukensha"]


def fresh_env(home: Path) -> None:
    """Pin HOME and clear every loader environment variable for one scenario."""
    os.environ["HOME"] = str(home)
    for name in ("BOUKENSHA_PATH", "BOUKENSHA_DIR", "BOUKENSHA_DEBUG"):
        os.environ.pop(name, None)


def make_step(root: Path, name: str, *, with_repl: bool) -> Path:
    """Create a step-shaped directory: ``<root>/<name>/boukensha/__init__.py``."""
    step = root / name
    pkg = step / "boukensha"
    pkg.mkdir(parents=True, exist_ok=True)
    body = ("def repl(*a, **k):\n    raise RuntimeError('offline: real repl must not run')\n"
            if with_repl else "value = 1\n")
    (pkg / "__init__.py").write_text(body)
    return step


def write_rc(home: Path, contents: str) -> None:
    (home / ".boukensharc").write_text(contents)


class ImportState:
    """Snapshot and restore the ``boukensha`` module tree and ``sys.path``.

    A boot test loads a fake step package by dropping the cached ``boukensha``
    tree and inserting the step directory on ``sys.path``. This restores the real
    installed package and the original path afterward so later checks are clean.
    """

    def __enter__(self):
        self._path = list(sys.path)
        self._modules = {k: v for k, v in sys.modules.items()
                         if k == "boukensha" or k.startswith("boukensha.")}
        return self

    def __exit__(self, *exc):
        sys.path[:] = self._path
        for key in [k for k in sys.modules if k == "boukensha" or k.startswith("boukensha.")]:
            del sys.modules[key]
        sys.modules.update(self._modules)
        sys.modules["boukensha"] = REAL_BOUKENSHA
        return False


def boot(step_env: dict, *, debug: bool = False, runner=None):
    """Drive ``load_and_start_repl`` with a recording runner and captured streams.

    Returns ``(received, out_text, err_text, aborted)`` where ``received`` is the
    module the runner was handed (or ``None`` if it was never called).
    """
    received = []
    out, err = io.StringIO(), io.StringIO()
    if debug:
        os.environ["BOUKENSHA_DEBUG"] = "1"
    aborted = False
    real_runner = runner if runner is not None else (lambda m: received.append(m))
    with ImportState():
        for key, value in step_env.items():
            os.environ[key] = value
        try:
            load_and_start_repl(repl_runner=real_runner, out=out, err=err)
        except SystemExit:
            aborted = True
    return (received[0] if received else None), out.getvalue(), err.getvalue(), aborted


def try_resolve():
    """Call ``resolve`` capturing stderr; return ``(value, err_text, aborted)``."""
    err = io.StringIO()
    try:
        return resolve(err=err), err.getvalue(), False
    except SystemExit:
        return None, err.getvalue(), True


def rel(path) -> str:
    """Render a temp path as ``$HOME/...`` so the demo output reads clearly."""
    if path is None:
        return "None (bundled)"
    home = os.environ["HOME"]
    return str(path).replace(home, "$HOME") if str(path).startswith(home) else str(path)


def head(title: str) -> None:
    print(f"\n-- {title} --")


def end_turn(text: str) -> tuple[int, str, dict]:
    """A canned Anthropic end_turn response for the offline stub transport."""
    body = json.dumps({
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": 120, "output_tokens": 24},
    })
    return 200, body, {}


class StubTransport:
    """A transport that returns canned HTTP responses, no network.

    Lets the real boot path (loader -> shadow-imported package -> a real turn)
    run offline, so the test proves the loaded implementation actually works,
    not merely that dispatch happened.
    """

    def __init__(self, *responses: tuple[int, str, dict]) -> None:
        self._responses = list(responses)

    def __call__(self, url, headers, body):
        return self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]


def run_live() -> None:
    """Headline: the installed command booting a live agent through the loader.

    Points ``BOUKENSHA_PATH`` at this step's own package and ``BOUKENSHA_DIR`` at
    the repo config, then boots one real REPL turn against the live provider, the
    exact path ``boukensha`` takes once installed. Gated so the suite stays offline
    by default.
    """
    print("=== boukensha · step 09: the global executable ===")
    print()
    print(f"  package version: {PKG_VERSION}   pyproject version: {PYPROJECT_VERSION}")
    print("  console script:  boukensha = boukensha.loader:main")
    print()
    if os.environ.get("BOUKENSHA_LIVE") != "1":
        print("Real boot gated: set BOUKENSHA_LIVE=1 (with a provider key) to have the")
        print("loader resolve this step, shadow-import it, and boot one live REPL turn.")
        print("The offline block below drives the same loader through every scenario.")
        return
    repo_cfg = STEP_DIR.parents[2] / ".boukensha"
    with ImportState():
        os.environ["BOUKENSHA_PATH"] = str(STEP_DIR)
        os.environ["BOUKENSHA_DIR"] = str(repo_cfg)
        script = "Look around this sunlit forest clearing and describe what you see.\n/exit\n"
        print("Booting via the loader (BOUKENSHA_PATH -> this step); one live turn:")
        print()
        load_and_start_repl(
            repl_runner=lambda module: module.repl(input=io.StringIO(script), output=sys.stdout),
            out=sys.stdout, err=sys.stderr,
        )


# ---------------------------------------------------------------------------
# Demo: drive the real loader through the scenarios the installed command hits.
# ---------------------------------------------------------------------------

run_live()

head("the loader through every scenario (offline)")
print("Each scenario below drives the real loader offline; the abort and debug")
print("lines shown are its actual output.")

DEMO_HOME = Path(tempfile.mkdtemp(prefix="boukensha-step09-demo-"))

head("an ~/.boukensharc names a step and a config directory")
fresh_env(DEMO_HOME)
d_step = make_step(DEMO_HOME, "07_the_run_dsl", with_repl=True)
write_rc(DEMO_HOME, f"boukensha_path: {d_step}\nboukensha_dir: config\n")
print("  ~/.boukensharc:")
print(f"    boukensha_path: {rel(d_step)}")
print("    boukensha_dir: config")
d_val, _, _ = try_resolve()
print(f"  resolve()            -> {rel(d_val)}")
print(f"  BOUKENSHA_DIR set to -> {rel(os.environ.get('BOUKENSHA_DIR'))}   (rc path, expanded from $HOME)")

head("an environment variable overrides the rc file")
fresh_env(DEMO_HOME)
env_step = make_step(DEMO_HOME, "08_the_repl_loop", with_repl=True)
write_rc(DEMO_HOME, f"boukensha_path: {d_step}\nboukensha_dir: rc-config\n")
os.environ["BOUKENSHA_PATH"] = str(env_step)
os.environ["BOUKENSHA_DIR"] = "/explicit/config"
print(f"  rc says   boukensha_path: {rel(d_step)}")
print(f"  env says  BOUKENSHA_PATH={rel(env_step)}  BOUKENSHA_DIR=/explicit/config")
d_val, _, _ = try_resolve()
print(f"  resolve()     -> {rel(d_val)}   (env won)")
print(f"  BOUKENSHA_DIR -> {os.environ.get('BOUKENSHA_DIR')}   (env won)")

head("no implementation selected falls back to the bundled package")
fresh_env(DEMO_HOME)
write_rc(DEMO_HOME, "")
d_val, _, _ = try_resolve()
print(f"  empty ~/.boukensharc -> resolve() = {rel(d_val)}")
print("  _import_impl then imports the installed boukensha package by name.")

head("boot dispatches to the resolved step's repl")
fresh_env(DEMO_HOME)
boot_step = make_step(DEMO_HOME, "with-a-repl", with_repl=True)


def announce(module):
    print(f"  repl_runner called with '{module.__name__}' from {rel(Path(module.__file__).parent.parent)}")
    print("  (the real command starts the interactive session here)")


boot({"BOUKENSHA_PATH": str(boot_step)}, runner=announce)

head("BOUKENSHA_DEBUG prints where the loader loaded from")
fresh_env(DEMO_HOME)
dbg_step = make_step(DEMO_HOME, "debug-step", with_repl=True)
_, _, err_text, _ = boot({"BOUKENSHA_PATH": str(dbg_step)}, debug=True)
print(f"  {err_text.strip().replace(str(DEMO_HOME), '$HOME')}")

head("bad configuration is rejected cleanly (expected, not a failure)")
print("  The loader refuses bad input with a clear, specific message. The")
print("  assertions below drive each case and pin its exact wording:")
print("    a step older than the REPL  ->  does not support the REPL, points at step 08+")
print("    a path with no boukensha/   ->  no boukensha/__init__.py, names the source")
print("    an rc that is a YAML list   ->  must be a mapping or a bare path string")
print("    an rc with invalid YAML     ->  invalid YAML, names the rc file")
print("    an rc with an unknown key   ->  unknown key, names it and the allowed keys")


# ---------------------------------------------------------------------------
# Assertions: the guarantees the demo showed, pinned. Compact, offline.
# ---------------------------------------------------------------------------

HOME = Path(tempfile.mkdtemp(prefix="boukensha-step09-"))

# 1: rc mapping resolves the step directory and sets BOUKENSHA_DIR home-relative.
fresh_env(HOME)
step1 = make_step(HOME, "configured-step", with_repl=True)
write_rc(HOME, f"boukensha_path: {step1}\nboukensha_dir: config\n")
val1, _, abort1 = try_resolve()
c1 = (not abort1 and val1 == str(step1)
      and os.environ.get("BOUKENSHA_DIR") == str(HOME / "config"))

# 2: env BOUKENSHA_PATH and BOUKENSHA_DIR each override their rc counterpart.
fresh_env(HOME)
rc_step = make_step(HOME, "rc-step", with_repl=True)
env_step = make_step(HOME, "env-step", with_repl=True)
write_rc(HOME, f"boukensha_path: {rc_step}\nboukensha_dir: rc-config\n")
os.environ["BOUKENSHA_PATH"] = str(env_step)
os.environ["BOUKENSHA_DIR"] = "/explicit/config"
val2, _, abort2 = try_resolve()
c2 = (not abort2 and val2 == str(env_step)
      and os.environ.get("BOUKENSHA_DIR") == "/explicit/config")

# 3: legacy bare-string rc resolves as boukensha_path.
fresh_env(HOME)
step3 = make_step(HOME, "legacy-step", with_repl=True)
write_rc(HOME, f"{step3}\n")
val3, _, abort3 = try_resolve()
c3 = (not abort3 and val3 == str(step3))

# 4: empty rc resolves to bundled (None).
fresh_env(HOME)
write_rc(HOME, "")
val4, _, abort4 = try_resolve()
c4 = (not abort4 and val4 is None)

# 5: BOUKENSHA_PATH at a directory without boukensha/__init__.py aborts, names it.
fresh_env(HOME)
bare = HOME / "not-a-step"
bare.mkdir(exist_ok=True)
os.environ["BOUKENSHA_PATH"] = str(bare)
val5, err5, abort5 = try_resolve()
c5 = (abort5 and str(bare) in err5 and "boukensha/__init__.py" in err5)

# 6: a non-mapping rc (a YAML list) aborts, naming the file and expected shape.
fresh_env(HOME)
write_rc(HOME, "- one\n- two\n")
val6, err6, abort6 = try_resolve()
c6 = (abort6 and str(HOME / ".boukensharc") in err6 and "mapping" in err6)

# 7: invalid YAML in the rc aborts, naming the file.
fresh_env(HOME)
write_rc(HOME, "boukensha_path: [unclosed\n")
val7, err7, abort7 = try_resolve()
c7 = (abort7 and str(HOME / ".boukensharc") in err7 and "invalid YAML" in err7)

# 8: rc paths expand relative to home; an env path expands relative to cwd.
fresh_env(HOME)
make_step(HOME, "rel-step", with_repl=True)
write_rc(HOME, "boukensha_path: rel-step\n")
val8a, _, abort8a = try_resolve()
cwd_root = Path(tempfile.mkdtemp(prefix="boukensha-step09-cwd-"))
make_step(cwd_root, "rel-env-step", with_repl=True)
fresh_env(HOME)
os.environ["BOUKENSHA_PATH"] = "rel-env-step"
prev_cwd = os.getcwd()
os.chdir(cwd_root)
val8b, _, abort8b = try_resolve()
os.chdir(prev_cwd)
c8 = (not abort8a and val8a == str(HOME / "rel-step")
      and not abort8b and val8b == str(cwd_root.resolve() / "rel-env-step"))

# 9: boot dispatches to the resolved implementation's repl via the injected runner.
fresh_env(HOME)
step9 = make_step(HOME, "repl-step", with_repl=True)
mod9, _, _, abort9 = boot({"BOUKENSHA_PATH": str(step9)})
c9 = (not abort9 and mod9 is not None and hasattr(mod9, "repl"))

# 10: an implementation with no repl aborts with the step-08 guidance, no dispatch.
fresh_env(HOME)
step10 = make_step(HOME, "no-repl-step", with_repl=False)
mod10, _, err10, abort10 = boot({"BOUKENSHA_PATH": str(step10)})
c10 = (abort10 and mod10 is None
       and "does not support the interactive REPL" in err10
       and "step 08" in err10)

# 11: BOUKENSHA_DEBUG set prints the loading-from line to stderr.
fresh_env(HOME)
step11 = make_step(HOME, "debug-step", with_repl=True)
_, _, err11, abort11 = boot({"BOUKENSHA_PATH": str(step11)}, debug=True)
c11 = (not abort11 and f"[boukensha] loading from: {step11}" in err11)

# 12: __version__ is 0.9.0 and equals the pyproject.toml version.
c12 = (PKG_VERSION == "0.9.0" and PYPROJECT_VERSION == "0.9.0")

# 13: booting a REAL package through the loader yields a working shadowed module,
# not merely a dispatch: a different module object, config that crossed the
# shadow boundary (the MUD host read from the injected BOUKENSHA_DIR), and a turn
# that completes against a stub transport.
real_home = Path(tempfile.mkdtemp(prefix="boukensha-step09-real-"))
fresh_env(real_home)
cfg13 = real_home / "config"
cfg13.mkdir()
(cfg13 / "settings.yaml").write_text(
    "tasks:\n  player:\n    provider: anthropic\n    model: claude-haiku-4-5\n"
    "mud:\n  host: moonlit-keep.example\n  port: 4321\n")
seen13: dict = {}
cap13 = io.StringIO()


def runner13(module):
    seen13["module"] = module
    seen13["mud_host"] = module.Config().mud_host
    module.repl(input=io.StringIO("look around\n/exit\n"), output=cap13,
                transport=StubTransport(end_turn("A quiet moonlit clearing.")),
                sleep=lambda _s: None)


_, _, _, abort13 = boot(
    {"BOUKENSHA_PATH": str(STEP_DIR), "BOUKENSHA_DIR": str(cfg13)}, runner=runner13)
c13 = (not abort13
       and seen13.get("module") is not None
       and seen13["module"] is not REAL_BOUKENSHA
       and seen13.get("mud_host") == "moonlit-keep.example"
       and "A quiet moonlit clearing." in cap13.getvalue())

# 14: an rc naming an unknown key aborts, naming the offending key, before any
# implementation loads (a typo in ~/.boukensharc fails loudly, not silently).
fresh_env(HOME)
write_rc(HOME, "boukensha_pth: /some/where\n")
val14, err14, abort14 = try_resolve()
c14 = (abort14 and "boukensha_pth" in err14 and "boukensha_path" in err14)

# 15: `boukensha --version` reports the command version and exits, never booting.
argv15, out15 = sys.argv, io.StringIO()
sys.argv = ["boukensha", "--version"]
prev_stdout = sys.stdout
sys.stdout = out15
booted15 = False
try:
    main()
    booted15 = True
except SystemExit as exc:
    code15 = exc.code
finally:
    sys.stdout, sys.argv = prev_stdout, argv15
c15 = (not booted15 and code15 == 0 and PKG_VERSION in out15.getvalue())

# 16: `python -m boukensha` runs the same entry point as the console script.
import subprocess  # noqa: E402
mod16 = subprocess.run(
    [sys.executable, "-m", "boukensha", "--version"],
    cwd=str(STEP_DIR), capture_output=True, text=True)
c16 = mod16.returncode == 0 and PKG_VERSION in mod16.stdout


checks = {
    "1 rc mapping resolves the step dir and sets BOUKENSHA_DIR to the home-relative path": c1,
    "2 env BOUKENSHA_PATH and BOUKENSHA_DIR each override their rc counterpart": c2,
    "3 the legacy bare-string rc resolves as boukensha_path": c3,
    "4 an empty rc resolves to bundled (resolve returns None)": c4,
    "5 a BOUKENSHA_PATH without boukensha/__init__.py aborts, naming the directory": c5,
    "6 a non-mapping rc (a YAML list) aborts, naming the file and the expected shape": c6,
    "7 invalid YAML in the rc aborts, naming the file": c7,
    "8 rc paths expand relative to home; an env path expands relative to the cwd": c8,
    "9 boot dispatches to the resolved implementation's repl via the injected runner": c9,
    "10 an implementation with no repl aborts with the step-08 guidance and never dispatches": c10,
    "11 BOUKENSHA_DEBUG set prints the loading-from line to stderr": c11,
    "12 __version__ is 0.9.0 and equals the pyproject.toml version": c12,
    "13 booting a real package shadows the module, crosses config, completes a turn": c13,
    "14 an rc with an unknown key aborts, naming the offending key, before loading": c14,
    "15 `boukensha --version` reports the version and exits without booting": c15,
    "16 `python -m boukensha --version` runs the same entry point, same version": c16,
}

head("assertions (offline)")
for label, passed in checks.items():
    print(f"  {'PASS' if passed else 'FAIL'} {label}")
assert all(checks.values()), "one or more loader guarantees failed"
print()
print("all loader guarantees hold")
