"""Phase 1 — health check smoke test. No database required."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_returns_ok() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body


@pytest.mark.asyncio
async def test_openapi_schema_is_accessible() -> None:
    """Verifies all router registrations succeed (import errors surface here)."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "Zoning Finder API"
    # All five routers should contribute paths
    paths = schema["paths"]
    assert "/health" in paths
    assert any("/jobs" in p for p in paths)
    assert any("/jurisdictions" in p for p in paths)
    assert any("/parcels" in p for p in paths)
    assert any("/shortlists" in p for p in paths)
