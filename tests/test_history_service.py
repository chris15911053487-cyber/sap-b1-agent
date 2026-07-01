import os
import tempfile
import pytest
import pytest_asyncio
from backend.services.history_service import HistoryService


@pytest_asyncio.fixture
async def history_service():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    svc = HistoryService(db_path=path)
    await svc.init()
    yield svc
    await svc.close()
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.mark.asyncio
async def test_create_conversation(history_service):
    conv_id = await history_service.create_conversation(database="test")
    assert conv_id is not None
    assert len(conv_id) == 36  # UUID format


@pytest.mark.asyncio
async def test_add_message(history_service):
    conv_id = await history_service.create_conversation(database="test")
    msg_id = await history_service.add_message(
        conversation_id=conv_id,
        role="user",
        content="查库存",
        intent="",
        sql="",
        data_json="",
    )
    assert msg_id is not None


@pytest.mark.asyncio
async def test_list_conversations(history_service):
    await history_service.create_conversation(database="test")
    await history_service.create_conversation(database="production")

    convs = await history_service.list_conversations(database="test")
    assert len(convs) == 1
    assert convs[0]["database"] == "test"


@pytest.mark.asyncio
async def test_list_conversations_all_databases(history_service):
    await history_service.create_conversation(database="test")
    await history_service.create_conversation(database="production")

    convs = await history_service.list_conversations()
    assert len(convs) == 2


@pytest.mark.asyncio
async def test_get_conversation_with_messages(history_service):
    conv_id = await history_service.create_conversation(database="test", title="库存查询")
    await history_service.add_message(
        conversation_id=conv_id, role="user", content="查库存",
        intent="", sql="", data_json="",
    )
    await history_service.add_message(
        conversation_id=conv_id, role="assistant", content="共有23种物料",
        intent="QUERY", sql="SELECT TOP 100 ...", data_json='{"columns":[],"rows":[]}',
    )

    conv = await history_service.get_conversation(conv_id)
    assert conv is not None
    assert conv["title"] == "库存查询"
    assert len(conv["messages"]) == 2
    assert conv["messages"][0]["role"] == "user"
    assert conv["messages"][1]["role"] == "assistant"
    assert conv["messages"][1]["intent"] == "QUERY"


@pytest.mark.asyncio
async def test_get_conversation_not_found(history_service):
    conv = await history_service.get_conversation("nonexistent-id")
    assert conv is None


@pytest.mark.asyncio
async def test_delete_conversation(history_service):
    conv_id = await history_service.create_conversation(database="test")
    await history_service.add_message(
        conversation_id=conv_id, role="user", content="test",
        intent="", sql="", data_json="",
    )

    await history_service.delete_conversation(conv_id)

    conv = await history_service.get_conversation(conv_id)
    assert conv is None

    convs = await history_service.list_conversations()
    assert len(convs) == 0


@pytest.mark.asyncio
async def test_message_count_accurate(history_service):
    conv_id = await history_service.create_conversation(database="test")
    await history_service.add_message(
        conversation_id=conv_id, role="user", content="m1",
        intent="", sql="", data_json="",
    )
    await history_service.add_message(
        conversation_id=conv_id, role="assistant", content="m2",
        intent="", sql="", data_json="",
    )
    await history_service.add_message(
        conversation_id=conv_id, role="user", content="m3",
        intent="", sql="", data_json="",
    )

    convs = await history_service.list_conversations()
    assert convs[0]["message_count"] == 3
