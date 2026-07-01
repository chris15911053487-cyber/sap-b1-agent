from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.middleware.error_handler import AppError, register_exception_handlers


def test_app_error_returns_unified_format():
    app = FastAPI()

    @app.get("/test-error")
    def raise_error():
        raise AppError("SOMETHING_BROKEN", "Something went wrong")

    register_exception_handlers(app)
    client = TestClient(app)

    response = client.get("/test-error")
    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "SOMETHING_BROKEN",
            "message": "Something went wrong",
        }
    }


def test_app_error_with_details():
    app = FastAPI()

    @app.get("/test-error-detail")
    def raise_error():
        raise AppError("VALIDATION_ERROR", "Invalid input", details={"field": "name"})

    register_exception_handlers(app)
    client = TestClient(app)

    response = client.get("/test-error-detail")
    assert response.status_code == 500
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert data["error"]["details"] == {"field": "name"}


def test_unhandled_exception_returns_generic_error():
    app = FastAPI()

    @app.get("/crash")
    def crash():
        raise RuntimeError("Unexpected internal error")

    register_exception_handlers(app)
    # raise_server_exceptions=False is required because Starlette's
    # ServerErrorMiddleware always re-raises after the handler runs,
    # which would otherwise prevent us from inspecting the response.
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/crash")
    assert response.status_code == 500
    data = response.json()
    assert data["error"]["code"] == "INTERNAL_ERROR"
    assert "Unexpected" not in data["error"]["message"]  # don't leak internal details
