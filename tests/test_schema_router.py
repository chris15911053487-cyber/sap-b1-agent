import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from fastapi import FastAPI
    from backend.middleware.error_handler import register_exception_handlers
    from backend.routers.schema import router

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)

    return TestClient(app)


def test_schema_tables_returns_core_tables(client):
    response = client.get("/api/schema/tables")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 6  # At least 6 core tables

    # Check structure of each table entry
    for table in data:
        assert "name" in table
        assert "description" in table
        assert "column_count" in table
        assert "columns" in table
        if table["columns"]:
            col = table["columns"][0]
            assert "name" in col
            assert "data_type" in col
            assert "description" in col

    # Verify specific core tables are present
    names = [t["name"] for t in data]
    for expected in ["OITM", "OCRD", "ORDR", "OINV", "OPOR", "OWOR"]:
        assert expected in names, f"Core table {expected} missing from response"
