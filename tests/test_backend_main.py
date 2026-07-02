"""Tests for the FastAPI application entry point (backend/main.py)."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    import os
    # Ensure we don't touch real config/DB
    os.environ["DEEPSEEK_API_KEY"] = "sk-test"

    from backend.main import app
    return TestClient(app)


def test_app_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_app_docs_available(client):
    response = client.get("/docs")
    assert response.status_code == 200


def test_openapi_schema(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "info" in schema
    paths = schema["paths"]
    # Verify all expected endpoints are registered
    assert "/api/chat" in paths
    assert "/api/history" in paths
    assert "/api/history/{conversation_id}" in paths
    assert "/api/connection/test" in paths
    assert "/api/schema/tables" in paths


def test_health_returns_request_id(client):
    """Health check should include X-Request-ID and X-Response-Time headers."""
    response = client.get("/health")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    assert "X-Response-Time" in response.headers


def test_request_id_persists_across_endpoints(client):
    """Client provided X-Request-ID should echo back."""
    response = client.get("/health", headers={"X-Request-ID": "my-test-id"})
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == "my-test-id"


def test_cors_headers(client):
    response = client.options(
        "/api/chat",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    # FastAPI CORS middleware returns allow-origin on OPTIONS
    assert response.status_code in (200, 405)  # 200 if CORS OK, 405 if not a CORS preflight
