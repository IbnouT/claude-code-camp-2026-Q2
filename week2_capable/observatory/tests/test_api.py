from __future__ import annotations

import httpx

from observatory_api.app import create_app
from observatory_api.settings import Settings


async def test_health_is_read_only(tmp_path):
    app = create_app(Settings(web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        response = await client.get("/api/health")
    assert response.json() == {"status": "ok", "read_only": True}


async def test_capabilities_are_honest_when_sources_are_absent(tmp_path):
    app = create_app(
        Settings(
            gateway_url="http://127.0.0.1:1",
            web_dist=tmp_path,
        )
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        response = await client.get("/api/capabilities")
    sources = {item["id"]: item for item in response.json()["sources"]}
    assert sources["gateway"]["state"] == "unavailable"
    assert sources["knowledge"]["state"] == "disabled"


async def test_missing_frontend_has_a_setup_action(tmp_path):
    app = create_app(Settings(web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        response = await client.get("/")
    assert response.status_code == 503
    assert response.json()["error"] == "frontend_not_built"


async def test_built_frontend_assets_are_served(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    (tmp_path / "index.html").write_text("<main>observatory</main>")
    (assets / "app.js").write_text("export const ready = true")
    app = create_app(Settings(web_dist=tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://observatory",
    ) as client:
        index = await client.get("/")
        asset = await client.get("/assets/app.js")
        missing = await client.get("/assets/not-there.js")
    assert index.status_code == 200
    assert asset.status_code == 200
    assert "ready = true" in asset.text
    assert missing.status_code == 404
