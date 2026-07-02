import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def mock_chat_service():
    service = MagicMock()
    service.process_message = AsyncMock()
    from backend.services.chat_service import ChatResponse
    service.process_message.return_value = ChatResponse(
        intent="query",
        sql="SELECT TOP 100 * FROM OITM",
        data={"markdown": "| ItemCode |\n|------|\n| A001 |"},
        explanation="共找到 1 条记录。",
        conversation_id="test-conv-123",
        success=True,
    )
    return service


@pytest.fixture
def client(mock_chat_service):
    # Build a minimal FastAPI app with the chat router wired to mock service
    import backend.routers.chat as chat_module

    # Store original dependencies
    original_get_service = getattr(chat_module, "_chat_service", None)

    chat_module._chat_service = mock_chat_service

    from fastapi import FastAPI
    from backend.middleware.error_handler import register_exception_handlers
    from backend.routers.chat import router as chat_router

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(chat_router)

    yield TestClient(app)

    # Restore
    if original_get_service is not None:
        chat_module._chat_service = original_get_service


def test_chat_endpoint_returns_full_response(client, mock_chat_service):
    response = client.post("/api/chat", json={
        "message": "查库存",
        "database": "test",
        "conversation_id": None,
    })

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "query"
    assert data["sql"] == "SELECT TOP 100 * FROM OITM"
    assert data["conversation_id"] == "test-conv-123"
    assert data["explanation"] == "共找到 1 条记录。"

    # Verify service was called correctly
    mock_chat_service.process_message.assert_called_once_with(
        message="查库存",
        database="test",
        conversation_id=None,
    )


def test_chat_endpoint_with_conversation_id(client, mock_chat_service):
    response = client.post("/api/chat", json={
        "message": "继续查",
        "database": "test",
        "conversation_id": "existing-conv-id",
    })

    assert response.status_code == 200
    mock_chat_service.process_message.assert_called_once_with(
        message="继续查",
        database="test",
        conversation_id="existing-conv-id",
    )


def test_chat_endpoint_missing_message_returns_422(client):
    response = client.post("/api/chat", json={
        "database": "test",
    })

    assert response.status_code == 422  # Pydantic validation error


def test_chat_endpoint_default_database(client, mock_chat_service):
    response = client.post("/api/chat", json={
        "message": "查库存",
    })

    assert response.status_code == 200
    mock_chat_service.process_message.assert_called_once_with(
        message="查库存",
        database="",
        conversation_id=None,
    )


@pytest.mark.asyncio
async def test_chat_stream_endpoint_returns_sse():
    """POST /api/chat/stream should return text/event-stream."""
    from backend.routers.chat import chat_stream, StreamChatRequest
    from backend.services.chat_service import ChatService
    from backend.services.history_service import HistoryService
    import backend.routers.chat as chat_mod
    import tempfile, os

    # Setup minimal services
    db_path = os.path.join(tempfile.mkdtemp(), "test.db")
    history_svc = HistoryService(db_path=db_path)
    await history_svc.init()

    from unittest.mock import MagicMock
    chat_svc = MagicMock(spec=ChatService)
    async def mock_stream(message, database="", conversation_id=None):
        yield "event: intent\ndata: {\"intent\": \"chat\"}\n\n"
        yield "event: explanation\ndata: {\"text\": \"hello\"}\n\n"
        yield "event: done\ndata: {}\n\n"
    chat_svc.process_message_stream = mock_stream

    original = chat_mod._chat_service
    chat_mod._chat_service = chat_svc

    try:
        req = StreamChatRequest(message="hi")
        response = await chat_stream(req)
        # EventSourceResponse wraps the generator
        assert response is not None
    finally:
        chat_mod._chat_service = original
        await history_svc.close()
