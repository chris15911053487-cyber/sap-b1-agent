"""Tests for /api/verify endpoint."""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def mock_config():
    """Mock load_config to return a config with test database only."""
    with patch("config.loader.load_config") as mock_load:
        from config.loader import DatabaseConfig

        mock_obj = MagicMock()
        mock_obj.agent.default_db = "test"
        mock_obj.databases = {
            "test": DatabaseConfig(
                type="sql_server",
                host="localhost",
                port=1433,
                database="SBO_TestDB",
                username="sa",
                password="test_password",
                timeout=10,
            ),
        }
        mock_load.return_value = mock_obj
        yield


@pytest.fixture
def verify_client(mock_config):
    """Create a TestClient with only the verify router."""
    from fastapi import FastAPI
    from backend.routers.verification import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_verify_returns_findings(verify_client):
    """POST /api/verify should return findings list even without DB."""
    response = verify_client.post("/api/verify", json={"database": "nonexistent"})
    assert response.status_code == 200
    data = response.json()
    assert "findings" in data
    assert "total_checks" in data
    assert data["total_checks"] > 0


def test_verify_response_structure(verify_client):
    """Verify response has expected fields."""
    response = verify_client.post("/api/verify", json={"database": "nonexistent"})
    data = response.json()
    assert "plan_name" in data
    assert "total_checks" in data
    assert "passed" in data
    assert "failed" in data
    assert "pass_rate" in data
    for finding in data["findings"]:
        assert "check_name" in finding
        assert "status" in finding
        assert "detail" in finding
