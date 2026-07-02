# Phase 5: 多轮对话 + 数据库切换 + 错误日志 优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable multi-turn conversation context (AI remembers previous exchanges), dynamic database switching (frontend loads available DBs from backend), and improved error logging with request tracing.

**Architecture:** ChatService loads recent messages from history and passes them to DBAgent, which injects prior exchanges into the LLM prompt. A new `GET /api/connection/databases` endpoint exposes configured databases. Frontend loads the database list dynamically. Logging gains request IDs and structured error context throughout the request pipeline.

**Tech Stack:** FastAPI middleware (request IDs), existing agent/history modules, Naive UI dynamic select

## Global Constraints

- Existing agent/, database/, config/ modules internal logic stays unchanged
- All new features are additive — no breaking changes to existing APIs
- Multi-turn context limited to last N exchanges (default 5) to avoid token bloat
- Tests must pass: `pytest tests/ -x -q`

---

### Task 1: Add `/api/connection/databases` endpoint and dynamic frontend selector

**Files:**
- Modify: `backend/routers/connection.py` (add databases endpoint)
- Modify: `frontend/src/api/types.ts` (add response type)
- Modify: `frontend/src/api/client.ts` (add API function)
- Modify: `frontend/src/stores/settings.ts` (dynamic database list)
- Modify: `frontend/src/components/LayoutHeader.vue` (dynamic select options)

- [ ] **Step 1: Add databases endpoint to connection router**

Read `backend/routers/connection.py` first. Add after the existing `test_connection` endpoint:

```python
from pydantic import BaseModel

class DatabaseInfo(BaseModel):
    name: str
    host: str
    port: int
    database: str

class DatabasesResponse(BaseModel):
    databases: list[DatabaseInfo]

@router.get("/connection/databases", response_model=DatabasesResponse)
async def list_databases() -> DatabasesResponse:
    """返回 config.yaml 中所有已配置的数据库列表（不含密码）."""
    from config.loader import load_config
    config = load_config(_get_config_path())
    result = []
    for name, db_cfg in config.databases.items():
        result.append(DatabaseInfo(
            name=name,
            host=db_cfg.host,
            port=db_cfg.port,
            database=db_cfg.database,
        ))
    return DatabasesResponse(databases=result)
```

- [ ] **Step 2: Add frontend types and API function**

In `frontend/src/api/types.ts`, add:
```typescript
export interface DatabaseInfo {
  name: string
  host: string
  port: number
  database: string
}
```

In `frontend/src/api/client.ts`, add:
```typescript
import type { DatabaseInfo } from './types'

export async function listDatabases(): Promise<DatabaseInfo[]> {
  const { data } = await api.get<{ databases: DatabaseInfo[] }>('/connection/databases')
  return data.databases
}
```

- [ ] **Step 3: Update settings store with dynamic database loading**

In `frontend/src/stores/settings.ts`, add:
```typescript
import { ref, onMounted } from 'vue'  // add onMounted
import { listDatabases } from '../api/client'
import type { DatabaseInfo } from '../api/types'

// Add to state:
const databases = ref<DatabaseInfo[]>([])
const databasesLoading = ref(false)

// Add loading function:
async function fetchDatabases() {
  databasesLoading.value = true
  try {
    databases.value = await listDatabases()
    // Auto-select first database if current selection not in list
    if (databases.value.length > 0 &&
        !databases.value.find(d => d.name === activeDatabase.value)) {
      activeDatabase.value = databases.value[0].name
    }
  } catch {
    // Keep hardcoded fallback
    databases.value = [
      { name: 'test', host: '', port: 0, database: '' },
      { name: 'production', host: '', port: 0, database: '' },
    ]
  } finally {
    databasesLoading.value = false
  }
}

// Export new state + function
return { ..., databases, databasesLoading, fetchDatabases }
```

- [ ] **Step 4: Update LayoutHeader to use dynamic options**

In `frontend/src/components/LayoutHeader.vue`, replace the hardcoded `databaseOptions`:
```typescript
import { computed, onMounted } from 'vue'

// Replace hardcoded array with computed from store:
const databaseOptions = computed(() =>
  settingsStore.databases.map(db => ({
    label: db.database ? `${db.name} (${db.database})` : db.name,
    value: db.name,
  }))
)

// Fetch databases on mount
onMounted(() => {
  settingsStore.fetchDatabases()
})
```

- [ ] **Step 5: Verify and commit**

```bash
cd frontend && npx vue-tsc --noEmit && npm run build
python3 -m pytest tests/ -x -q
```

Expected: all pass. Commit: `feat: dynamic database selector loading from backend config`

---

### Task 2: Multi-turn conversation context

**Files:**
- Modify: `agent/core.py` (accept optional `history` parameter)
- Modify: `agent/sql_generator.py` (inject history into prompt)
- Modify: `agent/interpreter.py` (optional context from history)
- Modify: `backend/services/chat_service.py` (load history, pass to agent)
- Create: `tests/test_multiturn.py`

- [ ] **Step 1: Add history parameter to DBAgent.process() and process_stream()**

In `agent/core.py`, modify both `process()` and `process_stream()` to accept an optional `history` parameter:

```python
def process(self, user_input: str, no_execute: bool = False,
            history: list[dict] | None = None) -> AgentResponse:
```

```python
async def process_stream(self, user_input: str,
                         history: list[dict] | None = None):
```

In `_stream_query()` and `_handle_query()`, pass `history` to `generate_sql()`:

```python
gen_result = generate_sql(
    user_input=user_input,
    schema_context=schema_context,
    api_key=self.api_key,
    model=self.config.agent.model,
    base_url=self.base_url,
    history=history,  # NEW
)
```

In `_handle_query()`, also pass to `interpret_query_result()`:

```python
explanation = interpret_query_result(
    result=query_result,
    user_question=user_input,
    api_key=self.api_key,
    model=self.config.agent.model,
    base_url=self.base_url,
    history=history,  # NEW
)
```

- [ ] **Step 2: Update generate_sql() to include history**

In `agent/sql_generator.py`, add `history` parameter:

```python
def generate_sql(
    user_input: str,
    schema_context: str,
    api_key: str,
    model: str = "deepseek-chat",
    base_url: str = "https://api.deepseek.com",
    history: list[dict] | None = None,
) -> SqlGenerationResult:
```

Update the `messages` array to include history:

```python
messages = []

# Add conversation history as context
if history:
    for h in history[-10:]:  # last 10 exchanges max
        role = h.get("role", "user")
        content = h.get("content", "")
        if role == "user":
            messages.append({"role": "user", "content": content})
        elif role == "assistant":
            # Include SQL + interpretation from previous responses
            prev_sql = h.get("sql", "")
            prev_intent = h.get("intent", "")
            parts = [content]
            if prev_sql:
                parts.append(f"\n[执行的SQL: {prev_sql}]")
            messages.append({"role": "assistant", "content": "\n".join(parts)})

# Add current prompt
messages.append({"role": "user", "content": prompt})
```

Use `messages=messages` instead of `messages=[{"role": "user", "content": prompt}]`.

- [ ] **Step 3: Update interpret_query_result() similarly**

```python
def interpret_query_result(
    result: QueryResult,
    user_question: str,
    api_key: str,
    model: str = "deepseek-chat",
    base_url: str = "https://api.deepseek.com",
    history: list[dict] | None = None,
) -> str:
```

Add history to messages array, then append the interpretation prompt.

- [ ] **Step 4: Load history in ChatService methods**

In `backend/services/chat_service.py`, both `process_message()` and `process_message_stream()`:

After resolving the conversation, load recent messages:
```python
# Load conversation history for multi-turn context
history_messages = []
if conversation_id:
    conv = await self.history.get_conversation(conversation_id)
    if conv and conv.get("messages"):
        history_messages = [
            {"role": m["role"], "content": m["content"],
             "sql": m.get("sql", ""), "intent": m.get("intent", "")}
            for m in conv["messages"]
        ]

# Pass to agent
agent_response = await asyncio.to_thread(
    agent.process, message, False, history_messages
)
```

And for streaming:
```python
async for event in agent.process_stream(message, history=history_messages):
```

- [ ] **Step 5: Add tests**

Create `tests/test_multiturn.py`:

```python
"""Tests for multi-turn conversation context."""
import pytest
from unittest.mock import MagicMock, patch


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

        # Verify messages include history
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args[1]["messages"]
        assert len(messages) >= 3  # history + current prompt
        # First message should be from history
        assert messages[0]["role"] == "user"
        assert "查库存" in messages[0]["content"]


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
        # 10 exchanges = 20 messages + 1 current prompt = 21 max
        # But since we slice only user/assistant from history[-10:], it's at most 10 entries + current
        assert len(messages) <= 11  # history[-10:] + current prompt
```

- [ ] **Step 6: Run tests and commit**

```bash
python3 -m pytest tests/ -x -q
```

Commit: `feat: multi-turn conversation context with history injection`

---

### Task 3: Error logging optimization

**Files:**
- Modify: `backend/main.py` (request ID middleware)
- Modify: `backend/middleware/error_handler.py` (structured errors)
- Modify: `backend/services/chat_service.py` (better error context)

- [ ] **Step 1: Add request ID middleware**

In `backend/main.py`, add after middleware imports:

```python
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import time

class RequestTracingMiddleware(BaseHTTPMiddleware):
    """注入 request_id 并记录请求耗时."""
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        request.state.request_id = request_id
        start = time.time()

        response = await call_next(request)

        elapsed = time.time() - start
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{elapsed:.3f}s"

        logger = logging.getLogger("api.request")
        logger.info(
            f"[{request_id}] {request.method} {request.url.path} "
            f"→ {response.status_code} ({elapsed:.3f}s)"
        )
        return response
```

Register after CORS middleware:
```python
app.add_middleware(RequestTracingMiddleware)
```

- [ ] **Step 2: Enhance error handler with request IDs**

In `backend/middleware/error_handler.py`, add request ID to error responses:

```python
from starlette.requests import Request

# In the exception handlers, extract request_id:
async def app_error_handler(request: Request, exc: AppError):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.error(f"[{request_id}] AppError: {exc.code} - {exc.message}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": request_id,
            }
        },
    )
```

- [ ] **Step 3: Add structured logging config**

Create module-level logging setup in `backend/main.py` (replace basic logging):

```python
import logging.config

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "detailed": {
            "format": "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "stream": "ext://sys.stdout",
        },
    },
    "root": {"level": "INFO", "handlers": ["console"]},
    "loggers": {
        "api.request": {"level": "INFO"},
        "backend": {"level": "DEBUG" if os.getenv("AGENT_ENV") == "development" else "INFO"},
        "agent": {"level": "INFO"},
    },
}

logging.config.dictConfig(LOGGING_CONFIG)
```

- [ ] **Step 4: Add tests for request ID**

Add to `tests/test_backend_main.py`:

```python
def test_health_returns_request_id():
    """Health check should include X-Request-ID header."""
    from fastapi.testclient import TestClient
    from backend.main import app

    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    assert "X-Response-Time" in response.headers
```

- [ ] **Step 5: Run tests and commit**

```bash
python3 -m pytest tests/ -x -q
```

Commit: `feat(backend): structured logging with request IDs and response timing`

---

### Task 4: End-to-end verification and progress update

- [ ] **Step 1: Run all tests**

```bash
python3 -m pytest tests/ -v
```

Expected: all pass (~118+)

- [ ] **Step 2: Frontend build**

```bash
cd frontend && npx vue-tsc --noEmit && npm run build
```

Expected: clean

- [ ] **Step 3: Update progress.md**

```bash
git add .superpowers/sdd/progress.md
git commit -m "docs: update progress — Phase 5 complete"
```
