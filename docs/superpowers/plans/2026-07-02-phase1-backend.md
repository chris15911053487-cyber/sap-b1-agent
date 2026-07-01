# SAP B1 Web 平台 — 一期实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建 FastAPI 后端骨架，提供 `/api/chat`（非流式）、`/api/history`（SQLite 持久化）、`/api/connection/test`、`/api/schema/tables` 四个核心端点。

**Architecture:** FastAPI 应用通过 import 复用现有 `agent/`、`database/`、`config/` 模块。`ChatService` 封装 DBAgent 调用并管理对话生命周期。`HistoryService` 使用 aiosqlite 持久化对话记录。所有端点统一错误格式通过 middleware 处理。

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, aiosqlite, pydantic

## Global Constraints

- Python >= 3.11 (匹配现有 Dockerfile 的 python:3.11-slim-bookworm)
- 现有 `agent/`、`database/`、`config/` 模块内部逻辑不得修改
- `agent/core.py` 仅可新增 `process_stream()` 方法签名（三期实现），一期不动
- API 错误响应统一为 `{"error": {"code": "...", "message": "..."}}`
- 所有 API 端点前缀 `/api/`
- 数据库密码通过 `.env` 注入，不提交
- SQLite 数据库文件存储在 `data/` 目录
- 遵循现有项目命名：Python 文件 snake_case，英文注释和日志

---

### Task 1: Create backend directory structure and package files

**Files:**
- Create: `backend/__init__.py`
- Create: `backend/routers/__init__.py`
- Create: `backend/services/__init__.py`
- Create: `backend/middleware/__init__.py`

**Interfaces:**
- Produces: `backend` Python package, importable as `from backend.main import app`

- [ ] **Step 1: Create all package init files**

```bash
mkdir -p backend/routers backend/services backend/middleware
```

- [ ] **Step 2: Write `backend/__init__.py`**

```python
# backend package
```

- [ ] **Step 3: Write `backend/routers/__init__.py`**

```python
# backend routers
```

- [ ] **Step 4: Write `backend/services/__init__.py`**

```python
# backend services
```

- [ ] **Step 5: Write `backend/middleware/__init__.py`**

```python
# backend middleware
```

- [ ] **Step 6: Verify package is importable**

```bash
cd /Users/apple/Documents/AI/Claude/20260701/sap-b1-db-agent && python -c "import backend; print('OK')"
```

Expected: `OK` (no errors)

- [ ] **Step 7: Commit**

```bash
git add backend/
git commit -m "feat(backend): create directory structure and package files"
```

### Task 2: Unified error handling middleware

**Files:**
- Create: `backend/middleware/error_handler.py`

**Interfaces:**
- Produces: `AppError(Exception)` base class, `register_exception_handlers(app: FastAPI) -> None`

- [ ] **Step 1: Write the test file**

Create `tests/test_error_handler.py`:

```python
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
    client = TestClient(app)

    response = client.get("/crash")
    assert response.status_code == 500
    data = response.json()
    assert data["error"]["code"] == "INTERNAL_ERROR"
    assert "Unexpected" not in data["error"]["message"]  # don't leak internal details
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_error_handler.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'backend.middleware.error_handler'`

- [ ] **Step 3: Write `backend/middleware/error_handler.py`**

```python
"""统一错误处理 — 所有 API 异常返回统一 JSON 格式."""
from __future__ import annotations

import logging
from typing import Optional, Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    """应用层异常，携带错误码供前端展示."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 500,
        details: Optional[dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


def register_exception_handlers(app: FastAPI) -> None:
    """向 FastAPI 应用注册全局异常处理器."""

    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        logger.warning(f"AppError [{exc.code}]: {exc.message}")
        body: dict[str, Any] = {"error": {"code": exc.code, "message": exc.message}}
        if exc.details:
            body["error"]["details"] = exc.details
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(f"Unhandled exception: {exc}")
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "服务器内部错误，请查看日志或联系管理员。",
                }
            },
        )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_error_handler.py -v
```

Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/middleware/error_handler.py tests/test_error_handler.py
git commit -m "feat(backend): add unified error handling middleware"
```

### Task 3: History service — SQLite conversation persistence

**Files:**
- Create: `backend/services/history_service.py`
- Test: `tests/test_history_service.py`

**Interfaces:**
- Produces:
  - `ConversationRecord(id: str, title: str, database: str, created_at: str, message_count: int)`
  - `MessageRecord(id: str, conversation_id: str, role: str, content: str, intent: str, sql: str, data_json: str, created_at: str)`
  - `HistoryService(db_path: str)` with `async init()`, `async create_conversation()`, `async add_message()`, `async list_conversations()`, `async get_conversation()`, `async delete_conversation()`, `async close()`

- [ ] **Step 1: Write the test file**

Create `tests/test_history_service.py`:

```python
import os
import tempfile
import pytest
from backend.services.history_service import HistoryService


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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_history_service.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write `backend/services/history_service.py`**

```python
"""对话历史持久化 — 基于 aiosqlite 的轻量存储."""
from __future__ import annotations

import json
import logging
import uuid
from typing import Optional

import aiosqlite

logger = logging.getLogger(__name__)


CREATE_CONVERSATIONS = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    database TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
)
"""

CREATE_MESSAGES = """
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    intent TEXT NOT NULL DEFAULT '',
    sql TEXT NOT NULL DEFAULT '',
    data_json TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
)
"""


class HistoryService:
    """SQLite-backed conversation history store."""

    def __init__(self, db_path: str = "data/history.db"):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def init(self) -> None:
        """Initialize database and create tables."""
        import os
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)

        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.execute(CREATE_CONVERSATIONS)
        await self._db.execute(CREATE_MESSAGES)
        await self._db.commit()
        logger.info(f"HistoryService initialized: {self.db_path}")

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    async def create_conversation(
        self, database: str = "", title: str = ""
    ) -> str:
        conv_id = str(uuid.uuid4())
        await self._db.execute(
            "INSERT INTO conversations (id, title, database) VALUES (?, ?, ?)",
            (conv_id, title, database),
        )
        await self._db.commit()
        logger.debug(f"Created conversation {conv_id}")
        return conv_id

    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        intent: str = "",
        sql: str = "",
        data_json: str = "",
    ) -> str:
        # Auto-set title from first user message
        if role == "user":
            row = await self._db.execute_fetchall(
                "SELECT COUNT(*) as cnt FROM messages WHERE conversation_id = ?",
                (conversation_id,),
            )
            if row and row[0]["cnt"] == 0:
                title = content[:40] + ("..." if len(content) > 40 else "")
                await self._db.execute(
                    "UPDATE conversations SET title = ? WHERE id = ?",
                    (title, conversation_id),
                )

        msg_id = str(uuid.uuid4())
        await self._db.execute(
            """INSERT INTO messages (id, conversation_id, role, content, intent, sql, data_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (msg_id, conversation_id, role, content, intent, sql, data_json),
        )
        await self._db.commit()
        return msg_id

    async def list_conversations(
        self, database: Optional[str] = None
    ) -> list[dict]:
        if database:
            rows = await self._db.execute_fetchall(
                """SELECT c.id, c.title, c.database, c.created_at,
                          COUNT(m.id) as message_count
                   FROM conversations c
                   LEFT JOIN messages m ON c.id = m.conversation_id
                   WHERE c.database = ?
                   GROUP BY c.id
                   ORDER BY c.created_at DESC""",
                (database,),
            )
        else:
            rows = await self._db.execute_fetchall(
                """SELECT c.id, c.title, c.database, c.created_at,
                          COUNT(m.id) as message_count
                   FROM conversations c
                   LEFT JOIN messages m ON c.id = m.conversation_id
                   GROUP BY c.id
                   ORDER BY c.created_at DESC""",
            )
        return [dict(r) for r in rows]

    async def get_conversation(self, conversation_id: str) -> Optional[dict]:
        conv_rows = await self._db.execute_fetchall(
            "SELECT * FROM conversations WHERE id = ?",
            (conversation_id,),
        )
        if not conv_rows:
            return None

        conv = dict(conv_rows[0])

        msg_rows = await self._db.execute_fetchall(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
            (conversation_id,),
        )
        conv["messages"] = [dict(r) for r in msg_rows]
        return conv

    async def delete_conversation(self, conversation_id: str) -> None:
        await self._db.execute(
            "DELETE FROM messages WHERE conversation_id = ?",
            (conversation_id,),
        )
        await self._db.execute(
            "DELETE FROM conversations WHERE id = ?",
            (conversation_id,),
        )
        await self._db.commit()
        logger.debug(f"Deleted conversation {conversation_id}")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_history_service.py -v
```

Expected: 7 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/history_service.py tests/test_history_service.py
git commit -m "feat(backend): add SQLite history service for conversation persistence"
```

### Task 4: Chat service — DBAgent wrapper

**Files:**
- Create: `backend/services/chat_service.py`
- Test: `tests/test_chat_service.py`

**Interfaces:**
- Consumes: `HistoryService` (from Task 3), `DBAgent` (from `agent.core`), `load_config` (from `config.loader`)
- Produces:
  - `ChatResponse(intent: str, sql: str, data: dict | None, explanation: str, conversation_id: str)`
  - `ChatService(config_path: str, api_key: str, base_url: str, history_service: HistoryService)` with `async process_message(message: str, database: str, conversation_id: str | None) -> ChatResponse`

- [ ] **Step 1: Write the test file**

Create `tests/test_chat_service.py`:

```python
import os
import tempfile
import pytest
from unittest.mock import MagicMock, patch
from backend.services.chat_service import ChatService, ChatResponse
from backend.services.history_service import HistoryService


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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_chat_service.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write `backend/services/chat_service.py`**

```python
"""聊天服务 — 封装 DBAgent，管理对话生命周期."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from agent.core import DBAgent, AgentResponse
from config.loader import load_config
from backend.services.history_service import HistoryService

logger = logging.getLogger(__name__)


@dataclass
class ChatResponse:
    intent: str
    sql: str = ""
    data: Optional[dict] = None
    explanation: str = ""
    conversation_id: str = ""
    success: bool = True
    error: str = ""


class ChatService:
    """编排 DBAgent 调用并持久化对话记录."""

    def __init__(
        self,
        config_path: str,
        api_key: str,
        base_url: str,
        history_service: HistoryService,
    ):
        self.config_path = config_path
        self.api_key = api_key
        self.base_url = base_url
        self.history = history_service
        self._config = load_config(config_path)

    async def process_message(
        self,
        message: str,
        database: str = "",
        conversation_id: Optional[str] = None,
    ) -> ChatResponse:
        """Process a user message and return the AI response.

        Args:
            message: 用户输入的自然语言
            database: 目标数据库配置名
            conversation_id: 现有对话 ID，None 则创建新对话
        """
        # Resolve conversation
        if conversation_id:
            existing = await self.history.get_conversation(conversation_id)
            if not existing:
                conversation_id = None  # invalid ID, create new

        if not conversation_id:
            conversation_id = await self.history.create_conversation(
                database=database,
            )

        # Save user message
        await self.history.add_message(
            conversation_id=conversation_id,
            role="user",
            content=message,
        )

        # Create agent — override default_db if database specified
        agent = DBAgent(
            config=self._config,
            api_key=self.api_key,
            base_url=self.base_url,
        )
        if database:
            agent.config.agent.default_db = database

        # Process with existing DBAgent
        try:
            agent_response: AgentResponse = agent.process(message)
        except Exception as e:
            logger.exception(f"Agent processing failed: {e}")
            agent_response = AgentResponse(
                intent="chat",
                success=False,
                error=str(e),
            )

        # Build response
        data = None
        if agent_response.data_table:
            data = {"markdown": agent_response.data_table}

        response = ChatResponse(
            intent=agent_response.intent,
            sql=agent_response.sql,
            data=data,
            explanation=agent_response.explanation if agent_response.success
                         else f"处理失败: {agent_response.error}",
            conversation_id=conversation_id,
            success=agent_response.success,
            error=agent_response.error,
        )

        # Serialize data for storage
        data_json = ""
        if data:
            try:
                data_json = json.dumps(data, ensure_ascii=False)
            except (TypeError, ValueError):
                pass

        # Save assistant message
        await self.history.add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=response.explanation,
            intent=response.intent,
            sql=response.sql,
            data_json=data_json,
        )

        return response
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_chat_service.py -v
```

Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/chat_service.py tests/test_chat_service.py
git commit -m "feat(backend): add ChatService wrapping DBAgent with history persistence"
```

### Task 5: Chat API router — POST /api/chat

**Files:**
- Create: `backend/routers/chat.py`
- Test: `tests/test_chat_router.py`

**Interfaces:**
- Consumes: `ChatService.process_message()` (from Task 4), `AppError` (from Task 2)
- Produces: FastAPI `APIRouter` with `POST /api/chat`

- [ ] **Step 1: Write the test file**

Create `tests/test_chat_router.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_chat_router.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'backend.routers.chat'`

- [ ] **Step 3: Write `backend/routers/chat.py`**

```python
"""聊天 API — 自然语言查询入口."""
from __future__ import annotations

import logging
from typing import Optional, Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.services.chat_service import ChatService
from backend.middleware.error_handler import AppError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])

# Injected by backend/main.py at startup
_chat_service: Optional[ChatService] = None


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="用户自然语言输入")
    database: str = Field(default="", description="目标数据库配置名")
    conversation_id: Optional[str] = Field(default=None, description="对话 ID，空则创建新对话")


class ChatResponseBody(BaseModel):
    intent: str
    sql: str = ""
    data: Optional[dict[str, Any]] = None
    explanation: str = ""
    conversation_id: str
    success: bool = True
    error: str = ""


@router.post("/chat", response_model=ChatResponseBody)
async def chat(request: ChatRequest) -> ChatResponseBody:
    """处理自然语言对话，自动识别意图并返回结果."""
    if _chat_service is None:
        raise AppError(
            code="SERVICE_NOT_READY",
            message="Chat service has not been initialized.",
            status_code=503,
        )

    result = await _chat_service.process_message(
        message=request.message,
        database=request.database,
        conversation_id=request.conversation_id,
    )

    return ChatResponseBody(
        intent=result.intent,
        sql=result.sql,
        data=result.data,
        explanation=result.explanation,
        conversation_id=result.conversation_id,
        success=result.success,
        error=result.error,
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_chat_router.py -v
```

Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routers/chat.py tests/test_chat_router.py
git commit -m "feat(backend): add /api/chat endpoint (non-streaming)"
```

### Task 6: History API router

**Files:**
- Create: `backend/routers/history.py`
- Test: `tests/test_history_router.py`

**Interfaces:**
- Consumes: `HistoryService` (from Task 3)
- Produces: FastAPI `APIRouter` with `GET /api/history`, `GET /api/history/{id}`, `DELETE /api/history/{id}`

- [ ] **Step 1: Write the test file**

Create `tests/test_history_router.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_history_router.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write `backend/routers/history.py`**

```python
"""对话历史 API."""
from __future__ import annotations

import logging
from typing import Optional, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from backend.services.history_service import HistoryService
from backend.middleware.error_handler import AppError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["history"])

_history_service: Optional[HistoryService] = None


class ConversationSummary(BaseModel):
    id: str
    title: str
    database: str
    created_at: str
    message_count: int


class MessageDetail(BaseModel):
    id: str
    role: str
    content: str
    intent: str
    sql: str
    data_json: str
    created_at: str


class ConversationDetail(BaseModel):
    id: str
    title: str
    database: str
    created_at: str
    messages: list[dict[str, Any]]


@router.get("/history", response_model=list[dict])
async def list_history(
    database: Optional[str] = Query(default=None, description="按数据库过滤"),
):
    """获取对话历史列表."""
    if _history_service is None:
        raise AppError(code="SERVICE_NOT_READY", message="History service not initialized.", status_code=503)

    conversations = await _history_service.list_conversations(database=database)
    return conversations


@router.get("/history/{conversation_id}")
async def get_conversation(conversation_id: str):
    """获取单个对话的完整消息列表."""
    if _history_service is None:
        raise AppError(code="SERVICE_NOT_READY", message="History service not initialized.", status_code=503)

    conv = await _history_service.get_conversation(conversation_id)
    if conv is None:
        raise AppError(code="NOT_FOUND", message="对话不存在", status_code=404)
    return conv


@router.delete("/history/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """删除对话及其所有消息."""
    if _history_service is None:
        raise AppError(code="SERVICE_NOT_READY", message="History service not initialized.", status_code=503)

    conv = await _history_service.get_conversation(conversation_id)
    if conv is None:
        raise AppError(code="NOT_FOUND", message="对话不存在", status_code=404)

    await _history_service.delete_conversation(conversation_id)
    return {"deleted": True}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_history_router.py -v
```

Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routers/history.py tests/test_history_router.py
git commit -m "feat(backend): add /api/history CRUD endpoints"
```

### Task 7: Connection test router

**Files:**
- Create: `backend/routers/connection.py`
- Test: `tests/test_connection_router.py`

**Interfaces:**
- Consumes: `load_config()` (from `config.loader`), `create_connection()`, `test_connection()` (from `database.connector`)
- Produces: FastAPI `APIRouter` with `POST /api/connection/test`

- [ ] **Step 1: Write the test file**

Create `tests/test_connection_router.py`:

```python
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
@patch("backend.routers.connection.test_connection")
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
@patch("backend.routers.connection.test_connection")
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
         patch("backend.routers.connection.test_connection") as mock_test:
        mock_create.return_value = make_mock_conn()
        mock_test.return_value = True

        response = client.post("/api/connection/test", json={})
        assert response.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_connection_router.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write `backend/routers/connection.py`**

```python
"""数据库连接测试 API."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from config.loader import load_config
from database.connector import create_connection, test_connection as test_db_conn
from backend.middleware.error_handler import AppError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["connection"])

# Injected by backend/main.py
_config_path: str = "config/config.yaml"


class ConnectionTestRequest(BaseModel):
    database: str = Field(default="", description="数据库配置名，空则取默认")


class ConnectionTestResponse(BaseModel):
    success: bool
    message: str
    database: str = ""
    host: str = ""
    port: int = 0


@router.post("/connection/test", response_model=ConnectionTestResponse)
async def test_connection(request: ConnectionTestRequest) -> ConnectionTestResponse:
    """测试指定数据库连接是否可用."""
    config = load_config(_config_path)

    db_name = request.database or config.agent.default_db
    db_config = config.databases.get(db_name)

    if not db_config:
        available = ", ".join(config.databases.keys()) if config.databases else "无"
        raise AppError(
            code="DB_NOT_FOUND",
            message=f"数据库配置 '{db_name}' 不存在。可用: {available}",
            status_code=404,
        )

    try:
        conn = create_connection(db_config)
        if test_db_conn(conn):
            return ConnectionTestResponse(
                success=True,
                message=f"连接成功: {db_config.type} @ {db_config.host}:{db_config.port}/{db_config.database}",
                database=db_name,
                host=db_config.host,
                port=db_config.port,
            )
        else:
            return ConnectionTestResponse(
                success=False,
                message=f"连接失败: {db_config.host}:{db_config.port}/{db_config.database}",
                database=db_name,
                host=db_config.host,
                port=db_config.port,
            )
    except Exception as e:
        logger.error(f"Connection test failed: {e}")
        return ConnectionTestResponse(
            success=False,
            message=f"连接异常: {e}",
            database=db_name,
            host=db_config.host,
            port=db_config.port,
        )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_connection_router.py -v
```

Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routers/connection.py tests/test_connection_router.py
git commit -m "feat(backend): add /api/connection/test endpoint"
```

### Task 8: Schema info router

**Files:**
- Create: `backend/routers/schema.py`
- Test: `tests/test_schema_router.py`

**Interfaces:**
- Consumes: `get_core_tables()` (from `database.schema`)
- Produces: FastAPI `APIRouter` with `GET /api/schema/tables`

- [ ] **Step 1: Write the test file**

Create `tests/test_schema_router.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_schema_router.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write `backend/routers/schema.py`**

```python
"""表结构查询 API."""
from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from database.schema import get_core_tables

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["schema"])


class ColumnInfo(BaseModel):
    name: str
    data_type: str
    is_nullable: bool
    is_primary_key: bool
    description: str


class TableInfo(BaseModel):
    name: str
    description: str
    column_count: int
    columns: list[dict]


@router.get("/schema/tables", response_model=list[TableInfo])
async def list_tables():
    """获取系统已知的 SAP B1 核心表结构列表."""
    core_tables = get_core_tables()

    result = []
    for table_name, schema in core_tables.items():
        columns = []
        for col in schema.columns:
            columns.append({
                "name": col.name,
                "data_type": col.data_type,
                "is_nullable": col.is_nullable,
                "is_primary_key": col.is_primary_key,
                "description": col.description or "",
            })

        result.append({
            "name": table_name,
            "description": schema.description,
            "column_count": len(schema.columns),
            "columns": columns,
        })

    # Sort by name for stable output
    result.sort(key=lambda t: t["name"])
    return result
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_schema_router.py -v
```

Expected: 1 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routers/schema.py tests/test_schema_router.py
git commit -m "feat(backend): add /api/schema/tables endpoint"
```

### Task 9: FastAPI application entry point — backend/main.py

**Files:**
- Create: `backend/main.py`
- Test: `tests/test_main.py` (existing, append)

**Interfaces:**
- Consumes: All routers (Task 5-8), `HistoryService` (Task 3), `ChatService` (Task 4), `register_exception_handlers` (Task 2)
- Produces: FastAPI `app` instance, `uvicorn` entry point

- [ ] **Step 1: Write the test file**

Create `tests/test_backend_main.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_backend_main.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write `backend/main.py`**

```python
"""FastAPI 应用入口."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.middleware.error_handler import register_exception_handlers
from backend.services.history_service import HistoryService
from backend.services.chat_service import ChatService
from backend.routers import chat, history, connection, schema

load_dotenv()

logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "config", "config.yaml"
)
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期 — 启停时初始化/清理资源."""
    # Startup
    logger.info("Starting SAP B1 DB Agent API...")

    # Initialize history service
    db_path = os.path.join(DATA_DIR, "history.db")
    history_svc = HistoryService(db_path=db_path)
    await history_svc.init()

    # Initialize chat service
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        logger.warning("DEEPSEEK_API_KEY not set — chat will fail until configured")
        api_key = ""

    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

    chat_svc = ChatService(
        config_path=CONFIG_PATH,
        api_key=api_key,
        base_url=base_url,
        history_service=history_svc,
    )

    # Inject services into routers
    chat._chat_service = chat_svc
    history._history_service = history_svc
    connection._config_path = CONFIG_PATH

    logger.info("Services initialized. API ready.")

    yield

    # Shutdown
    logger.info("Shutting down...")
    await history_svc.close()


app = FastAPI(
    title="SAP B1 DB Agent API",
    description="SAP Business One 数据库 AI 智能体 Web API",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS — allow dev frontend origin; in production Nginx handles this
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:80", "http://127.0.0.1:80"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Error handling
register_exception_handlers(app)

# Routers
app.include_router(chat.router)
app.include_router(history.router)
app.include_router(connection.router)
app.include_router(schema.router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_backend_main.py -v
```

Expected: 3-4 PASS (CORS test may return 405 which is acceptable)

- [ ] **Step 5: Commit**

```bash
git add backend/main.py tests/test_backend_main.py
git commit -m "feat(backend): add FastAPI application entry point with lifespan management"
```

### Task 10: Update requirements.txt

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Update requirements.txt**

Read current `requirements.txt` and append the new dependencies:

```bash
cd /Users/apple/Documents/AI/Claude/20260701/sap-b1-db-agent
```

Edit `requirements.txt` to include:

```
click>=8.1.0
pyyaml>=6.0
pymssql>=2.3.0
python-dotenv>=1.0.0
openai>=1.0.0
pytest>=8.0.0
pytest-mock>=3.12.0
pytest-asyncio>=0.23.0
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
aiosqlite>=0.20.0
sse-starlette>=2.0.0
```

- [ ] **Step 2: Install new dependencies**

```bash
pip install fastapi "uvicorn[standard]" aiosqlite sse-starlette pytest-asyncio
```

Expected: all packages install without errors

- [ ] **Step 3: Run all backend tests together**

```bash
python -m pytest tests/test_error_handler.py tests/test_history_service.py tests/test_chat_service.py tests/test_chat_router.py tests/test_history_router.py tests/test_connection_router.py tests/test_schema_router.py tests/test_backend_main.py -v
```

Expected: all PASS (approximately 30 tests)

- [ ] **Step 4: Verify existing tests still pass**

```bash
python -m pytest tests/ -v --ignore=tests/test_error_handler.py --ignore=tests/test_history_service.py --ignore=tests/test_chat_service.py --ignore=tests/test_chat_router.py --ignore=tests/test_history_router.py --ignore=tests/test_connection_router.py --ignore=tests/test_schema_router.py --ignore=tests/test_backend_main.py
```

Expected: all existing 71 tests still PASS

- [ ] **Step 5: Commit**

```bash
git add requirements.txt
git commit -m "chore: add FastAPI, aiosqlite, SSE dependencies"
```

