import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from fastapi import FastAPI
    from backend.middleware.error_handler import register_exception_handlers
    from backend.routers.connection import router

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)

    return TestClient(app)


def make_mock_conn():
    """Create a mock connection that passes test_connection."""
    mock = MagicMock()
    return mock


@patch("backend.routers.connection.load_config")
@patch("backend.routers.connection.create_connection")
@patch("backend.routers.connection.test_db_conn")
def test_connection_success(mock_test, mock_create, mock_load, client):
    from config.loader import AppConfig, AgentConfig, DatabaseConfig

    mock_load.return_value = AppConfig(
        databases={"test": DatabaseConfig(
            type="sql_server", host="localhost", port=1433,
            database="TESTDB", username="sa", password="pass",
        )},
        agent=AgentConfig(default_db="test"),
    )
    mock_create.return_value = make_mock_conn()
    mock_test.return_value = True

    response = client.post("/api/connection/test", json={"database": "test"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "连接成功" in data["message"]


@patch("backend.routers.connection.load_config")
@patch("backend.routers.connection.create_connection")
@patch("backend.routers.connection.test_db_conn")
def test_connection_failure(mock_test, mock_create, mock_load, client):
    from config.loader import AppConfig, AgentConfig, DatabaseConfig

    mock_load.return_value = AppConfig(
        databases={"test": DatabaseConfig(
            type="sql_server", host="localhost", port=1433,
            database="TESTDB", username="sa", password="pass",
        )},
    )
    mock_create.return_value = make_mock_conn()
    mock_test.return_value = False

    response = client.post("/api/connection/test", json={"database": "test"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False


@patch("backend.routers.connection.load_config")
def test_connection_unknown_database(mock_load, client):
    from config.loader import AppConfig

    mock_load.return_value = AppConfig(databases={})

    response = client.post("/api/connection/test", json={"database": "unknown"})
    assert response.status_code == 404


@patch("backend.routers.connection.load_config")
def test_connection_default_db(mock_load, client):
    from config.loader import AppConfig, AgentConfig, DatabaseConfig

    mock_load.return_value = AppConfig(
        databases={"test": DatabaseConfig(
            type="sql_server", host="localhost", port=1433,
            database="TESTDB", username="sa", password="pass",
        )},
        agent=AgentConfig(default_db="test"),
    )

    with patch("backend.routers.connection.create_connection") as mock_create, \
         patch("backend.routers.connection.test_db_conn") as mock_test:
        mock_create.return_value = make_mock_conn()
        mock_test.return_value = True

        response = client.post("/api/connection/test", json={})
        assert response.status_code == 200
