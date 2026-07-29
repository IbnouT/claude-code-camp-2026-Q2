"""The tracked agent configuration names the installed Week 2 gateway."""

import tomllib
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


class TestGatewayCutover(unittest.TestCase):
    def test_default_configuration_selects_the_installed_direct_full_surface(self):
        settings = yaml.safe_load(
            (ROOT / ".boukensha" / "settings.yaml").read_text()
        )
        entry = settings["mcp_servers"]["mud"]
        self.assertEqual("boukensha-gateway", entry["command"])
        self.assertEqual(["--profile", "direct-full"], entry["args"])

    def test_gateway_package_declares_the_configured_command(self):
        project = tomllib.loads(
            (
                ROOT / "week2_capable" / "gateway" / "pyproject.toml"
            ).read_text()
        )
        scripts = project["project"]["scripts"]
        self.assertEqual(
            "mud_gateway.mcp_server:main",
            scripts["boukensha-gateway"],
        )
        self.assertEqual(
            "admin_process.server:main",
            scripts["boukensha-gateway-admin"],
        )


if __name__ == "__main__":
    unittest.main()
