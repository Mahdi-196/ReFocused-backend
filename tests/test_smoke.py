import asyncio
import os
import pytest
import httpx


@pytest.mark.asyncio
async def test_health_endpoint_running_locally():
    # If running in CI without server, just validate that the route exists by starting a test app instance
    from app.main_production import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        res = client.get("/health")
        assert res.status_code in (200, 503)


@pytest.mark.asyncio
async def test_metrics_endpoint_exists():
    from app.main_production import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        res = client.get("/metrics")
        assert res.status_code == 200
        assert "http_requests_total" in res.text


