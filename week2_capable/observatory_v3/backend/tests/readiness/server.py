"""Serve the production bundle against a fresh B9 retained fixture."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import uvicorn

from observatory_v3_backend.app import create_app
from observatory_v3_backend.settings import Settings

from .fixture import build_readiness_fixture


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4175)
    parser.add_argument("--web-dist", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    """Run one disposable, model-free production-browser scenario."""
    arguments = _parse_args()
    with tempfile.TemporaryDirectory(
        prefix="observatory-browser-readiness-"
    ) as directory:
        fixture = build_readiness_fixture(Path(directory))
        application = create_app(
            Settings(
                runtime_root=fixture.retained.config_dir,
                web_dist=arguments.web_dist,
            )
        )
        uvicorn.run(
            application,
            host=arguments.host,
            port=arguments.port,
            log_level="warning",
        )


if __name__ == "__main__":
    main()
