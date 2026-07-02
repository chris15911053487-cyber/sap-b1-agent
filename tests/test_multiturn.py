"""Tests for multi-turn conversation context.

Verifies that conversation history is passed through the full processing chain:
  core.py -> sql_generator.py / interpreter.py -> LLM API call.
"""
import os
import tempfile
import pytest
import pytest_asyncio
from unittest.mock import MagicMock, patch, ANY
from agent.core import AgentResponse
from config.loader import AppConfig, AgentConfig


# Ensure env vars are set so config.example.yaml can be loaded
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
def app_config():
    return AppConfig(
        databases={},
        agent=AgentConfig(
            default_db="test",
            model="deepseek-chat",
            max_query_rows=100,
            log_level="DEBUG",
            locale="zh_CN",
        ),
    )


@pytest_asyncio.fixture
async def history_service():
    """Temporary SQLite-backed HistoryService for testing."""
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
def mock_agent():
    """Mock DBAgent with a pre-configured return value."""
    with patch("backend.services.chat_service.DBAgent") as mock:
        agent_instance = MagicMock()
        mock.return_value = agent_instance
        agent_instance.process.return_value = AgentResponse(
            intent="query",
            success=True,
            sql="SELECT TOP 100 * FROM OITM",
            data_table="| ItemCode | ItemName |\n|------|------|\n| A001 | 物料A |",
            explanation="共找到 1 条物料记录。",
        )
        yield agent_instance

# ---------------------------------------------------------------------------
# sql_generator: generate_sql() history injection
# ---------------------------------------------------------------------------


def test_generate_sql_includes_history_in_messages():
    """generate_sql should include history messages in the API call."""
    from agent.sql_generator import generate_sql

    history = [
        {"role": "user", "content": "查库存", "sql": "", "intent": "query"},
        {"role": "assistant", "content": "库存如下...", "sql": "SELECT ...", "intent": "query"},
        {"role": "user", "content": "只看北京的", "sql": "", "intent": "query"},
    ]

    with patch("agent.sql_generator.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_choice = MagicMock()
        mock_choice.message.content = '{"sql": "SELECT 1", "explanation": "test"}'
        mock_client.chat.completions.create.return_value.choices = [mock_choice]

        generate_sql(
            user_input="只看北京的",
            schema_context="test schema",
            api_key="test-key",
            model="test-model",
            history=history,
        )

        call_args = mock_client.chat.completions.create.call_args
        messages = call_args[1]["messages"]
        assert len(messages) >= 3  # history + current prompt
        # First message should be from history (user question)
        assert messages[0]["role"] == "user"
        assert "查库存" in messages[0]["content"]


def test_generate_sql_injects_assistant_sql_in_history():
    """Assistant messages in history should include [执行的SQL: ...] when sql is present."""
    from agent.sql_generator import generate_sql

    history = [
        {"role": "user", "content": "查库存", "sql": "", "intent": "query"},
        {"role": "assistant", "content": "库存如下", "sql": "SELECT * FROM OITM", "intent": "query"},
    ]

    with patch("agent.sql_generator.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_choice = MagicMock()
        mock_choice.message.content = '{"sql": "SELECT 1", "explanation": "test"}'
        mock_client.chat.completions.create.return_value.choices = [mock_choice]

        generate_sql(
            user_input="只看北京的",
            schema_context="test",
            api_key="test-key",
            history=history,
        )

        messages = mock_client.chat.completions.create.call_args[1]["messages"]
        # Assistant message should include SQL reference
        assert messages[1]["role"] == "assistant"
        assert "[执行的SQL: SELECT * FROM OITM]" in messages[1]["content"]


def test_generate_sql_limits_history_to_last_10():
    """generate_sql should limit history to last 10 exchanges."""
    from agent.sql_generator import generate_sql

    history = []
    for i in range(20):
        history.append({"role": "user", "content": f"msg {i}", "sql": "", "intent": "query"})
        history.append({"role": "assistant", "content": f"reply {i}", "sql": "SELECT 1", "intent": "query"})

    with patch("agent.sql_generator.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_choice = MagicMock()
        mock_choice.message.content = '{"sql": "SELECT 1", "explanation": "test"}'
        mock_client.chat.completions.create.return_value.choices = [mock_choice]

        generate_sql(
            user_input="latest query",
            schema_context="test",
            api_key="test-key",
            history=history,
        )

        messages = mock_client.chat.completions.create.call_args[1]["messages"]
        # 10 exchanges = 10 messages + 1 current prompt = 11 max
        assert len(messages) <= 11


def test_generate_sql_no_history():
    """generate_sql works without history (regression for single-turn)."""
    from agent.sql_generator import generate_sql

    with patch("agent.sql_generator.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_choice = MagicMock()
        mock_choice.message.content = '{"sql": "SELECT 1", "explanation": "ok"}'
        mock_client.chat.completions.create.return_value.choices = [mock_choice]

        result = generate_sql(
            user_input="hello",
            schema_context="test",
            api_key="test-key",
        )
        assert result.success
        assert result.sql == "SELECT 1"

        messages = mock_client.chat.completions.create.call_args[1]["messages"]
        assert len(messages) == 1  # only current prompt


def test_generate_sql_empty_history():
    """generate_sql with empty history list should behave like no history."""
    from agent.sql_generator import generate_sql

    with patch("agent.sql_generator.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_choice = MagicMock()
        mock_choice.message.content = '{"sql": "SELECT 1", "explanation": "ok"}'
        mock_client.chat.completions.create.return_value.choices = [mock_choice]

        result = generate_sql(
            user_input="hello",
            schema_context="test",
            api_key="test-key",
            history=[],
        )
        assert result.success
        assert result.sql == "SELECT 1"

        messages = mock_client.chat.completions.create.call_args[1]["messages"]
        assert len(messages) == 1  # only current prompt


# ---------------------------------------------------------------------------
# interpreter: interpret_query_result() history injection
# ---------------------------------------------------------------------------


def test_interpret_query_result_includes_history():
    """interpret_query_result should include history messages in the API call."""
    from agent.interpreter import interpret_query_result

    history = [
        {"role": "user", "content": "上月销售额", "sql": "", "intent": "query"},
        {"role": "assistant", "content": "上月销售额是100万", "sql": "SELECT ...", "intent": "query"},
    ]

    result = type("QueryResult", (), {
        "columns": ["Total"],
        "rows": [(150000,)],
        "row_count": 1,
        "success": True,
    })()

    with patch("agent.interpreter.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_choice = MagicMock()
        mock_choice.message.content = "解读内容"
        mock_client.chat.completions.create.return_value.choices = [mock_choice]

        interpret_query_result(
            result=result,
            user_question="上月销售额",
            api_key="test-key",
            model="test-model",
            history=history,
        )

        call_args = mock_client.chat.completions.create.call_args
        messages = call_args[1]["messages"]
        assert len(messages) >= 2
        # First message should be from history
        assert messages[0]["role"] == "user"
        assert "上月销售额" in messages[0]["content"]


def test_interpret_query_result_no_history():
    """interpret_query_result works without history (regression)."""
    from agent.interpreter import interpret_query_result

    result = type("QueryResult", (), {
        "columns": ["Total"],
        "rows": [(150000,)],
        "row_count": 1,
        "success": True,
    })()

    with patch("agent.interpreter.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_choice = MagicMock()
        mock_choice.message.content = "解读内容"
        mock_client.chat.completions.create.return_value.choices = [mock_choice]

        text = interpret_query_result(
            result=result,
            user_question="上月销售额",
            api_key="test-key",
        )

        assert text == "解读内容"

        messages = mock_client.chat.completions.create.call_args[1]["messages"]
        assert len(messages) == 1  # only interpretation prompt


# ---------------------------------------------------------------------------
# core.py: DBAgent.process() and process_stream() history passthrough
# ---------------------------------------------------------------------------


def test_process_passes_history_to_generate_sql(app_config):
    """DBAgent.process() should pass history through to generate_sql."""
    from agent.core import DBAgent

    agent = DBAgent(config=app_config, api_key="test-key")

    history = [
        {"role": "user", "content": "之前的问题", "sql": "", "intent": "query"},
        {"role": "assistant", "content": "之前的回答", "sql": "SELECT 1", "intent": "query"},
    ]

    # Patch at the generate_sql level inside module where it's imported
    with patch("agent.core.generate_sql") as mock_gen:
        mock_gen.return_value = type("SqlGenerationResult", (), {
            "sql": "SELECT TOP 100 * FROM OITM",
            "explanation": "查询物料",
            "success": True,
        })()

        agent.process("查物料", history=history)

    # Verify generate_sql received history
    _, kwargs = mock_gen.call_args
    assert kwargs.get("history") == history


def test_process_passes_history_to_interpret_query_result(app_config):
    """DBAgent.process() should pass history through to interpret_query_result
    when a database connection is available."""
    from agent.core import DBAgent

    agent = DBAgent(config=app_config, api_key="test-key")

    history = [
        {"role": "user", "content": "之前的问题", "sql": "", "intent": "query"},
        {"role": "assistant", "content": "之前的回答", "sql": "SELECT 1", "intent": "query"},
    ]

    with patch("agent.core.generate_sql") as mock_gen:
        mock_gen.return_value = type("SqlGenerationResult", (), {
            "sql": "SELECT TOP 100 * FROM OITM",
            "explanation": "查询物料",
            "success": True,
        })()

        with patch("agent.core.create_connection") as mock_conn:
            with patch("agent.core.execute_query") as mock_exec:
                mock_exec.return_value = type("QueryResult", (), {
                    "columns": ["ItemCode"],
                    "rows": [("A001",)],
                    "row_count": 1,
                    "success": True,
                    "error": "",
                })()

                with patch("agent.core.interpret_query_result") as mock_int:
                    mock_int.return_value = "解读成功"
                    # Add a db config so we hit the execution path
                    from config.loader import DatabaseConfig
                    agent.config.databases["test_db"] = DatabaseConfig(
                        type="sql_server",
                        host="localhost",
                        port=1433,
                        database="SBO",
                        username="sa",
                        password="pwd",
                    )
                    agent.config.agent.default_db = "test_db"
                    agent.process("查物料", history=history)

    # Verify interpret_query_result received history
    _, int_kwargs = mock_int.call_args
    assert int_kwargs.get("history") == history


def test_process_no_history(app_config):
    """DBAgent.process() works without history (regression)."""
    from agent.core import DBAgent

    agent = DBAgent(config=app_config, api_key="test-key")

    with patch("agent.core.generate_sql") as mock_gen:
        mock_gen.return_value = type("SqlGenerationResult", (), {
            "sql": "SELECT TOP 100 * FROM OITM",
            "explanation": "查询物料",
            "success": True,
        })()

        with patch("agent.core.interpret_query_result") as mock_int:
            mock_int.return_value = "解读成功"
            response = agent.process("查物料")

    assert response.success
    assert response.sql == "SELECT TOP 100 * FROM OITM"

    # Should not have passed history
    _, kwargs = mock_gen.call_args
    assert kwargs.get("history") is None


@pytest.mark.asyncio
async def test_process_stream_passes_history(app_config):
    """DBAgent.process_stream() should pass history to generate_sql and interpret."""
    from agent.core import DBAgent

    agent = DBAgent(config=app_config, api_key="test-key")

    history = [
        {"role": "user", "content": "之前的问题", "sql": "", "intent": "query"},
        {"role": "assistant", "content": "之前的回答", "sql": "SELECT 1", "intent": "query"},
    ]

    with patch("agent.core.generate_sql") as mock_gen:
        mock_gen.return_value = type("SqlGenerationResult", (), {
            "sql": "SELECT TOP 100 * FROM OITM",
            "explanation": "test",
            "success": True,
        })()

        with patch("agent.core.interpret_query_result") as mock_int:
            mock_int.return_value = "解读成功"

            # Consume the generator (needs a default_db that matches a config entry)
            # Since app_config has default_db="test" and no databases, it'll fall to
            # the unconnected path, which is fine.
            events = []
            async for event in agent.process_stream("查物料", history=history):
                events.append(event)

    # Verify history was passed to generate_sql
    _, gen_kwargs = mock_gen.call_args
    assert gen_kwargs.get("history") == history

    # interpret_query_result won't be called if no db connection, but the history
    # parameter is still wired; at least verify generate_sql got it


# ---------------------------------------------------------------------------
# chat_service: history loading from conversation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_service_loads_history_for_existing_conversation(history_service, mock_agent):
    """ChatService should load history from existing conversation and pass to agent."""
    from backend.services.chat_service import ChatService

    # Create a conversation with some history
    conv_id = await history_service.create_conversation(database="test")
    await history_service.add_message(conv_id, "user", "查库存", sql="", intent="query")
    await history_service.add_message(conv_id, "assistant", "库存如下", sql="SELECT * FROM OITM", intent="query")

    svc = ChatService(
        config_path="config/config.example.yaml",
        api_key="sk-test",
        base_url="https://api.deepseek.com",
        history_service=history_service,
    )

    response = await svc.process_message(
        message="只看北京的",
        database="test",
        conversation_id=conv_id,
    )

    # Verify history was passed to agent.process()
    # The mock_agent instance is our agent_instance
    assert mock_agent.process.call_count > 0
    call_args, call_kwargs = mock_agent.process.call_args
    # agent.process receives (message, no_execute, history) as positional args
    assert len(call_args) >= 3
    history_arg = call_args[2]
    assert isinstance(history_arg, list)
    assert len(history_arg) >= 2
    # First history entry should be the user message
    assert history_arg[0]["role"] == "user"
    assert history_arg[0]["content"] == "查库存"
    # Second should be the assistant response
    assert history_arg[1]["role"] == "assistant"
    assert history_arg[1]["sql"] == "SELECT * FROM OITM"


@pytest.mark.asyncio
async def test_chat_service_history_includes_previous_messages(history_service, mock_agent):
    """History should include all previous messages (including just-saved current one)."""
    from backend.services.chat_service import ChatService

    conv_id = await history_service.create_conversation(database="test")
    await history_service.add_message(conv_id, "user", "查库存", sql="", intent="query")
    await history_service.add_message(conv_id, "assistant", "库存如下", sql="SELECT 1", intent="query")

    svc = ChatService(
        config_path="config/config.example.yaml",
        api_key="sk-test",
        base_url="https://api.deepseek.com",
        history_service=history_service,
    )

    await svc.process_message(
        message="只看北京的",
        database="test",
        conversation_id=conv_id,
    )

    call_args, _ = mock_agent.process.call_args
    history_arg = call_args[2]
    # History includes all messages (previous + just-saved current)
    contents = [h["content"] for h in history_arg]
    assert "查库存" in contents  # previous message
    assert "库存如下" in contents  # previous response
    assert "只看北京的" in contents  # current message (saved before loading)


@pytest.mark.asyncio
async def test_chat_service_new_conversation_has_only_current_message(history_service, mock_agent):
    """New conversations should pass history with only the current message (just-saved)."""
    from backend.services.chat_service import ChatService

    svc = ChatService(
        config_path="config/config.example.yaml",
        api_key="sk-test",
        base_url="https://api.deepseek.com",
        history_service=history_service,
    )

    await svc.process_message(
        message="查库存",
        database="test",
        conversation_id=None,
    )

    call_args, _ = mock_agent.process.call_args
    history_arg = call_args[2]
    # The current message was saved before loading history, so it appears
    assert len(history_arg) == 1
    assert history_arg[0]["role"] == "user"
    assert history_arg[0]["content"] == "查库存"


@pytest.mark.asyncio
async def test_chat_service_stream_loads_history(history_service, mock_agent):
    """process_message_stream should also load history and pass to agent."""
    from backend.services.chat_service import ChatService

    conv_id = await history_service.create_conversation(database="test")
    await history_service.add_message(conv_id, "user", "之前的查询", sql="", intent="query")

    svc = ChatService(
        config_path="config/config.example.yaml",
        api_key="sk-test",
        base_url="https://api.deepseek.com",
        history_service=history_service,
    )

    # Consume the stream generator
    events = []
    async for event in svc.process_message_stream(
        message="后续查询",
        database="test",
        conversation_id=conv_id,
    ):
        events.append(event)

    # Verify history was passed
    assert mock_agent.process_stream.call_count > 0
    _, stream_kwargs = mock_agent.process_stream.call_args
    history_arg = stream_kwargs.get("history", [])
    assert isinstance(history_arg, list)
    assert len(history_arg) >= 1
    assert history_arg[0]["content"] == "之前的查询"
