import os
import tempfile
import pytest
from fastapi.testclient import TestClient

import backend.routers.history as history_module


@pytest.fixture
async def history_service():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    from backend.services.history_service import HistoryService
    svc = HistoryService(db_path=path)
    await svc.init()
    yield svc
    await svc.close()
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def client(history_service):
    history_module._history_service = history_service

    from fastapi import FastAPI
    from backend.middleware.error_handler import register_exception_handlers
    from backend.routers.history import router

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)

    return TestClient(app)


def test_list_history_empty(client):
    response = client.get("/api/history")
    assert response.status_code == 200
    assert response.json() == []


def test_list_history_with_data(client, history_service):
    import asyncio

    async def seed():
        cid = await history_service.create_conversation(database="test", title="库存查询")
        await history_service.add_message(
            conversation_id=cid, role="user", content="查库存",
            intent="", sql="", data_json="",
        )
        return cid

    asyncio.get_event_loop().run_until_complete(seed())

    response = client.get("/api/history")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["title"] == "库存查询"
    assert data[0]["message_count"] == 1


def test_list_history_filter_by_database(client, history_service):
    import asyncio

    async def seed():
        await history_service.create_conversation(database="test", title="测试库对话")
        await history_service.create_conversation(database="production", title="生产库对话")

    asyncio.get_event_loop().run_until_complete(seed())

    response = client.get("/api/history?database=test")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["title"] == "测试库对话"


def test_get_conversation_detail(client, history_service):
    import asyncio

    async def seed():
        cid = await history_service.create_conversation(database="test")
        await history_service.add_message(
            conversation_id=cid, role="user", content="用户消息",
            intent="", sql="", data_json="",
        )
        await history_service.add_message(
            conversation_id=cid, role="assistant", content="AI 回复",
            intent="QUERY", sql="SELECT 1", data_json='{"a":1}',
        )
        return cid

    cid = asyncio.get_event_loop().run_until_complete(seed())

    response = client.get(f"/api/history/{cid}")
    assert response.status_code == 200
    data = response.json()
    assert len(data["messages"]) == 2
    assert data["messages"][1]["intent"] == "QUERY"


def test_get_conversation_not_found(client):
    response = client.get("/api/history/nonexistent-id")
    assert response.status_code == 404


def test_delete_conversation(client, history_service):
    import asyncio

    async def seed():
        cid = await history_service.create_conversation(database="test")
        return cid

    cid = asyncio.get_event_loop().run_until_complete(seed())

    response = client.delete(f"/api/history/{cid}")
    assert response.status_code == 200
    assert response.json() == {"deleted": True}

    # Verify it's gone
    response = client.get(f"/api/history/{cid}")
    assert response.status_code == 404
