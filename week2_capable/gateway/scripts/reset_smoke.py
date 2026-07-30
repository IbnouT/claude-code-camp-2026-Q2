"""Apply two resets through one selected live gateway and compare receipts."""

from __future__ import annotations

import argparse
from pathlib import Path

from mud_gateway.reset_client import request_reset


def gate(session_dir: Path) -> int:
    first = request_reset(session_dir)
    second = request_reset(session_dir)
    first_state = first.get("state")
    second_state = second.get("state")
    differences = {} if first_state == second_state else {
        "state": (first_state, second_state)
    }
    passed = (
        first.get("ok") is True
        and second.get("ok") is True
        and not differences
    )
    print(
        f"  first reset  : ok={first.get('ok')} "
        f"unread={first.get('unread')}"
    )
    print(
        f"  second reset : ok={second.get('ok')} "
        f"unread={second.get('unread')}"
    )
    print(f"  differences  : {differences}")
    print(f"\n  RESET SMOKE: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--session-dir",
        type=Path,
        required=True,
        help="selected live .boukensha/profiles/<player>/sessions/<session>",
    )
    arguments = parser.parse_args()
    raise SystemExit(gate(arguments.session_dir))


if __name__ == "__main__":
    main()
