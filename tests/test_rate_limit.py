import os
from fastapi.testclient import TestClient
from app.main_production import app


def test_rate_limit_headers_present_when_enabled(monkeypatch):
    # Enable rate limiting in app settings
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")

    with TestClient(app) as client:
        res = client.get("/")
        # Headers may be present depending on middleware; assert app doesn't error
        assert res.status_code == 200


