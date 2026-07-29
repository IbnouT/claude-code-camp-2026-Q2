"""The registry covers installed-manager evidence without mirroring its API."""

import json
import pathlib

from mud_gateway.commands import BY_NAME
from mud_gateway.profiles import PROFILES

REFERENCE = pathlib.Path(__file__).parent / "fixtures" / "mud_manager_tools.json"
REFERENCE_NAMES = {
    tool["name"] for tool in json.loads(REFERENCE.read_text(encoding="utf-8"))
}


def test_registry_covers_every_evidenced_mortal_capability():
    assert REFERENCE_NAMES <= set(BY_NAME)


def test_default_full_profile_covers_the_evidence():
    assert REFERENCE_NAMES <= PROFILES["direct-full"].allowed


def test_raw_is_supported_but_denied_by_default():
    assert "send_raw" in BY_NAME
    assert "send_raw" not in PROFILES["direct-full"].allowed


def test_observe_and_navigate_are_our_extensions_not_reference_tools():
    assert {"observe", "navigate"} <= set(BY_NAME)
    assert not {"observe", "navigate"} & REFERENCE_NAMES
