"""Report gateway capability coverage against recorded manager evidence."""

from __future__ import annotations

import json
from pathlib import Path

from mud_gateway.commands import BY_NAME
from mud_gateway.profiles import PROFILES, Surface


def comparable(schema: dict[str, object]) -> dict[str, object]:
    properties = schema.get("properties", {})
    assert isinstance(properties, dict)
    return {
        "properties": {
            name: {
                key: value
                for key, value in definition.items()
                if key in {"type", "enum", "default"}
            }
            for name, definition in properties.items()
        },
        "required": sorted(schema.get("required", [])),
    }


def main() -> None:
    reference_path = (
        Path(__file__).resolve().parents[1]
        / "tests"
        / "fixtures"
        / "mud_manager_tools.json"
    )
    reference = json.loads(reference_path.read_text())
    agent_reference = [tool for tool in reference if tool["name"] != "send_raw"]
    residual = []
    for tool in agent_reference:
        name = tool["name"]
        if name not in BY_NAME or comparable(
            tool["inputSchema"]
        ) != comparable(BY_NAME[name].schema()["inputSchema"]):
            residual.append(name)
    surface = Surface(PROFILES["direct-full"])
    print(
        json.dumps(
            {
                "reference_capabilities": len(reference),
                "agent_reference_capabilities": len(agent_reference),
                "agent_covered": len(agent_reference) - len(residual),
                "argument_shape_matches": len(agent_reference) - len(residual),
                "coverage": (
                    0.0
                    if not agent_reference
                    else (len(agent_reference) - len(residual))
                    / len(agent_reference)
                ),
                "advertised_tools": len(surface.schemas()),
                "raw_registered": "send_raw" in BY_NAME,
                "raw_advertised": "send_raw" in surface.profile.allowed,
                "residual": residual,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
