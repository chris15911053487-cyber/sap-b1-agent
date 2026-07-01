import os
import tempfile
import pytest
from unittest.mock import MagicMock, patch
from backend.services.chat_service import ChatService, ChatResponse
from backend.services.history_service import HistoryService

# Set dummy env vars so config.example.yaml can be loaded during tests
os.environ.setdefault("DB_TEST_HOST", "localhost")
os.environ.setdefault("DB_TEST_PORT", "1433")
os.environ.setdefault("DB_TEST_NAME", "testdb")
os.environ.setdefault("DB_TEST_USER", "sa")
os.environ.setdefault("DB_TEST_PASSWORD", "password")
os.environ.setdefault("DB_PROD_HOST", "prod-host")
os.environ.setdefault("DB_PROD_PORT", "1433")
os.environ.setdefault("DB_PROD_NAME", "proddb")
os.environ.setdefault("DB_PROD_USER", "sa")
os.environ.setdefault("DB_PROD_PASSWORD", "password")


@pytest.fixture
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


@pytest.fixture
def mock_agent():
    with patch("backend.services.chat_service.DBAgent") as mock:
        agent_instance = MagicMock()
        mock.return_value = agent_instance

        from agent.core import AgentResponse
        agent_instance.process.return_value = AgentResponse(
            intent="query",
            success=True,
            sql="SELECT TOP 100 * FROM OITM",
            data_table="| ItemCode | ItemName |\n|------|------|\n| A001 | 物料A |",
            explanation="共找到 1 条物料记录。",
        )
        yield agent_instance


@pytest.mark.asyncio
async def test_process_message_creates_new_conversation(history_service, mock_agent):
    svc = ChatService(
        config_path="config/config.example.yaml",
        api_key="sk-test",
        base_url="https://api.deepseek.com",
        history_service=history_service,
    )

    response = await svc.process_message(
        message="查库存",
        database="test",
        conversation_id=None,
    )

    assert isinstance(response, ChatResponse)
    assert response.intent == "query"
    assert response.sql == "SELECT TOP 100 * FROM OITM"
    assert response.conversation_id is not None
    assert len(response.conversation_id) == 36

    # Verify conversation was saved
    conv = await history_service.get_conversation(response.conversation_id)
    assert conv is not None
    assert len(conv["messages"]) == 2  # user + assistant
    assert conv["messages"][0]["role"] == "user"
    assert conv["messages"][0]["content"] == "查库存"
    assert conv["messages"][1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_process_message_appends_to_existing_conversation(history_service, mock_agent):
    conv_id = await history_service.create_conversation(database="test")

    svc = ChatService(
        config_path="config/config.example.yaml",
        api_key="sk-test",
        base_url="https://api.deepseek.com",
        history_service=history_service,
    )

    response = await svc.process_message(
        message="再查一下销售订单",
        database="test",
        conversation_id=conv_id,
    )

    assert response.conversation_id == conv_id

    # Verify messages appended
    conv = await history_service.get_conversation(conv_id)
    assert len(conv["messages"]) == 2  # user + assistant


@pytest.mark.asyncio
async def test_process_message_invalid_conversation_creates_new(history_service, mock_agent):
    svc = ChatService(
        config_path="config/config.example.yaml",
        api_key="sk-test",
        base_url="https://api.deepseek.com",
        history_service=history_service,
    )

    response = await svc.process_message(
        message="查库存",
        database="test",
        conversation_id="nonexistent-id",
    )

    # Should create a new conversation instead of failing
    assert response.conversation_id != "nonexistent-id"


@pytest.mark.asyncio
async def test_process_message_returns_error_on_agent_failure(history_service, mock_agent):
    from agent.core import AgentResponse
    mock_agent.process.return_value = AgentResponse(
        intent="query",
        success=False,
        error="API rate limit exceeded",
    )

    svc = ChatService(
        config_path="config/config.example.yaml",
        api_key="sk-test",
        base_url="https://api.deepseek.com",
        history_service=history_service,
    )

    response = await svc.process_message(
        message="查库存",
        database="test",
        conversation_id=None,
    )

    assert response.intent == "query"
    assert "失败" in response.explanation or "错误" in response.explanation or response.explanation != ""
