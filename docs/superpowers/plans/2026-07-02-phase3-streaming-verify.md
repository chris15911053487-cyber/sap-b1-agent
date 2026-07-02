# Phase 3: 流式输出 + 数据校验 + 设置增强 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add SSE streaming chat, data verification UI, and enhanced settings — delivering the complete user experience.

**Architecture:** Backend adds a `process_stream()` async generator to DBAgent that yields progressive SSE events (intent → sql → data → explanation → done), a corresponding `/api/chat/stream` endpoint, and a `/api/verify` endpoint for standalone verification. Frontend adds SSE client support in the API layer, progressive message rendering in the chat store, a VerifyView with check cards, and enhanced SettingsView.

**Tech Stack:** FastAPI + sse-starlette (backend streaming), Naive UI + EventSource (frontend), existing agent/ modules unchanged beyond adding `process_stream()`.

## Global Constraints

- Existing `agent/`, `database/`, `config/` modules internal logic stays unchanged — only `agent/core.py` gets a new `process_stream()` method
- Frontend stays pure static SPA, proxy `/api` through Vite dev server
- All API responses follow existing error format `{"error": {"code": "...", "message": "..."}}`
- SSE uses `text/event-stream` with named events matching design spec: `intent`, `sql`, `data`, `explanation`, `done`
- Tests must pass before commit: `pytest tests/ -x -q`

---

### Task 1: Add `process_stream()` async generator to DBAgent

**Files:**
- Modify: `agent/core.py`

**Interfaces:**
- Produces: `DBAgent.process_stream(self, user_input: str) -> AsyncGenerator[str, None]` — yields SSE event strings

- [ ] **Step 1: Add `process_stream()` method**

Add after the existing `process()` method in `DBAgent` (line 56):

```python
    async def process_stream(self, user_input: str):
        """异步流式处理用户输入，逐事件 yield SSE 格式字符串。

        事件类型：
        - intent: 意图识别结果
        - sql: 生成的 SQL
        - data: 查询/校验结果数据
        - explanation: 中文解读
        - done: 处理完成
        - error: 错误信息
        """
        import json
        from agent.intent import Intent as IntentEnum, analyze_intent as _analyze

        intent_result = _analyze(user_input)
        logger.info(
            f"Intent: {intent_result.intent.value} "
            f"(confidence: {intent_result.confidence:.2f})"
        )
        yield f"event: intent\ndata: {json.dumps({'intent': intent_result.intent.value, 'confidence': intent_result.confidence})}\n\n"

        if intent_result.intent == IntentEnum.QUERY:
            async for event in self._stream_query(user_input):
                yield event
        elif intent_result.intent == IntentEnum.BUILD_SP:
            async for event in self._stream_build_sp(user_input):
                yield event
        elif intent_result.intent == IntentEnum.VERIFY:
            async for event in self._stream_verify(user_input):
                yield event
        else:
            async for event in self._stream_chat(user_input):
                yield event

        yield f"event: done\ndata: {{}}\n\n"
```

- [ ] **Step 2: Add `_stream_query()` private method**

```python
    async def _stream_query(self, user_input: str):
        import json

        schema_context = self._get_schema_context()

        gen_result = generate_sql(
            user_input=user_input,
            schema_context=schema_context,
            api_key=self.api_key,
            model=self.config.agent.model,
            base_url=self.base_url,
        )

        if not gen_result.success:
            yield f"event: error\ndata: {json.dumps({'error': gen_result.error})}\n\n"
            return

        yield f"event: sql\ndata: {json.dumps({'sql': gen_result.sql})}\n\n"

        db_name = self.config.agent.default_db
        db_config = self.config.databases.get(db_name)
        if db_config:
            conn = create_connection(db_config)
            try:
                query_result = execute_query(
                    conn,
                    gen_result.sql,
                    max_rows=self.config.agent.max_query_rows,
                )

                if query_result.success:
                    data_table = format_result_as_markdown_table(query_result)
                    yield f"event: data\ndata: {json.dumps({'markdown': data_table})}\n\n"

                    explanation = interpret_query_result(
                        result=query_result,
                        user_question=user_input,
                        api_key=self.api_key,
                        model=self.config.agent.model,
                        base_url=self.base_url,
                    )
                    yield f"event: explanation\ndata: {json.dumps({'text': explanation})}\n\n"
                else:
                    error_msg = f"SQL 执行出错: {query_result.error}"
                    yield f"event: error\ndata: {json.dumps({'error': error_msg})}\n\n"
            finally:
                close_connection(conn)
        else:
            yield f"event: data\ndata: {json.dumps({'markdown': ''})}\n\n"
            yield f"event: explanation\ndata: {json.dumps({'text': f\"SQL 已生成（未连接数据库）:\\n```sql\\n{gen_result.sql}\\n```\\n\\n{gen_result.explanation}\"})}\n\n"
```

- [ ] **Step 3: Add `_stream_build_sp()` private method**

```python
    async def _stream_build_sp(self, user_input: str):
        import json

        schema_context = self._get_schema_context()
        design_prompt = build_sp_design_prompt(
            requirement=user_input,
            schema_context=schema_context,
        )

        text = (
            f"## 存储过程体系设计 Prompt\n\n"
            f"已根据您的需求构建完整的设计 Prompt，请将以下内容提供给 AI 进行存储过程架构设计:\n\n"
            f"```\n{design_prompt}\n```\n\n"
            f"### 后续步骤\n"
            f"1. 将上述 Prompt 提交给 AI 模型生成 SP 架构设计\n"
            f"2. 审核生成的 JSON 架构设计\n"
            f"3. 逐个生成 T-SQL 代码\n"
            f"4. 在数据库上部署验证"
        )
        yield f"event: explanation\ndata: {json.dumps({'text': text})}\n\n"
```

- [ ] **Step 4: Add `_stream_verify()` private method**

```python
    async def _stream_verify(self, user_input: str):
        import json

        checks = generate_standard_inventory_checks()

        db_name = self.config.agent.default_db
        db_config = self.config.databases.get(db_name)
        if not db_config:
            yield f"event: explanation\ndata: {json.dumps({'text': f'## 标准验证方案\\n\\n已验证检查项: {len(checks)} 项\\n\\n未连接数据库，请在连接后重试。'})}\n\n"
            return

        from agent.verifier import VerificationFinding

        conn = create_connection(db_config)
        try:
            findings = []
            for check in checks:
                result = execute_query(conn, check.check_sql)
                if not result.success:
                    findings.append(VerificationFinding(
                        check_name=check.name,
                        status="error",
                        detail=f"执行失败: {result.error}",
                    ))
                elif result.row_count == 0:
                    findings.append(VerificationFinding(
                        check_name=check.name,
                        status="pass",
                        detail="检查通过，未发现异常",
                    ))
                else:
                    findings.append(VerificationFinding(
                        check_name=check.name,
                        status="fail",
                        detail=f"发现 {result.row_count} 条异常数据",
                    ))
        finally:
            close_connection(conn)

        report = VerificationReport(plan_name="数据验证", findings=findings)

        # Yield individual check results
        findings_json = [
            {
                "check_name": f.check_name,
                "status": f.status,
                "detail": f.detail,
            }
            for f in report.findings
        ]
        yield f"event: data\ndata: {json.dumps({'findings': findings_json, 'pass_rate': report.pass_rate, 'total': report.total_checks, 'passed': report.passed, 'failed': report.failed})}\n\n"
        yield f"event: explanation\ndata: {json.dumps({'text': report.summary_text()})}\n\n"
```

- [ ] **Step 5: Add `_stream_chat()` private method**

```python
    async def _stream_chat(self, user_input: str):
        import json

        result = self._handle_chat(user_input)
        yield f"event: explanation\ndata: {json.dumps({'text': result.explanation})}\n\n"
```

- [ ] **Step 6: Run existing tests to verify no regressions**

```bash
cd /Users/apple/Documents/AI/Claude/20260701/sap-b1-db-agent && python -m pytest tests/ -x -q
```

Expected: all existing tests pass (the new `process_stream()` is additive, no existing logic changed)

- [ ] **Step 7: Add unit test for `process_stream()`**

Create: `tests/test_core_stream.py`

```python
"""Tests for DBAgent.process_stream() async generator."""
import pytest
from unittest.mock import patch, MagicMock
from agent.core import DBAgent, AgentResponse


@pytest.mark.asyncio
async def test_process_stream_yields_intent_event():
    """process_stream should yield an intent event first."""
    from config.loader import AppConfig, AgentConfig

    config = AppConfig(
        agent=AgentConfig(model="test-model", default_db="test", max_query_rows=10),
        databases={"test": MagicMock()},
    )
    agent = DBAgent(config=config, api_key="test-key", base_url="https://test.api")

    events = []
    async for event in agent.process_stream("你好"):
        events.append(event)

    # First event should be intent
    assert events[0].startswith("event: intent\n")
    # Last event should be done
    assert events[-1].startswith("event: done\n")


@pytest.mark.asyncio
async def test_process_stream_chat_yields_explanation():
    """CHAT intent should yield explanation then done."""
    from config.loader import AppConfig, AgentConfig

    config = AppConfig(
        agent=AgentConfig(model="test-model", default_db="test", max_query_rows=10),
        databases={"test": MagicMock()},
    )
    agent = DBAgent(config=config, api_key="test-key", base_url="https://test.api")

    events = []
    async for event in agent.process_stream("你好"):
        events.append(event)

    # Should have at least: intent, explanation, done
    event_types = []
    for e in events:
        if e.startswith("event: "):
            event_types.append(e.split("\n")[0].replace("event: ", ""))
    assert "intent" in event_types
    assert "explanation" in event_types
    assert "done" in event_types
```

- [ ] **Step 8: Run new tests**

```bash
cd /Users/apple/Documents/AI/Claude/20260701/sap-b1-db-agent && python -m pytest tests/test_core_stream.py -x -v
```

Expected: 2 passed

- [ ] **Step 9: Commit**

```bash
git add agent/core.py tests/test_core_stream.py
git commit -m "feat(agent): add process_stream() async generator for SSE streaming"
```

---

### Task 2: Add `process_message_stream()` to ChatService and SSE endpoint

**Files:**
- Modify: `backend/services/chat_service.py`
- Modify: `backend/routers/chat.py`

**Interfaces:**
- Consumes: `DBAgent.process_stream(user_input)` from Task 1
- Produces: `ChatService.process_message_stream(message, database, conversation_id) -> AsyncGenerator[str, None]`, `POST /api/chat/stream` SSE endpoint

- [ ] **Step 1: Add streaming method to ChatService**

In `backend/services/chat_service.py`, add after `process_message()`:

```python
    async def process_message_stream(
        self,
        message: str,
        database: str = "",
        conversation_id: Optional[str] = None,
    ):
        """流式处理用户消息，逐事件 yield SSE 字符串。

        与 process_message() 相同的逻辑，但通过 DBAgent.process_stream()
        逐事件转发，同时在完成时持久化对话记录。
        """
        import json as _json

        # Resolve conversation
        if conversation_id:
            existing = await self.history.get_conversation(conversation_id)
            if not existing:
                conversation_id = None

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

        # Create agent
        agent = DBAgent(
            config=self._config,
            api_key=self.api_key,
            base_url=self.base_url,
        )
        if database:
            if database not in self._config.databases:
                raise AppError(
                    code="DB_NOT_FOUND",
                    message=f"数据库 '{database}' 不存在",
                    status_code=404,
                )
            agent.config = copy.deepcopy(agent.config)
            agent.config.agent.default_db = database

        # Collect response fields from SSE events
        collected = {
            "intent": "",
            "sql": "",
            "data_markdown": "",
            "explanation": "",
            "error": "",
        }

        # Forward agent stream, inject conversation_id on first event
        first_event = True
        async for event in agent.process_stream(message):
            if first_event:
                # Inject conversation_id into the intent event data
                if event.startswith("event: intent\n"):
                    prefix = "event: intent\ndata: "
                    payload = event[len(prefix):].strip()
                    try:
                        data = _json.loads(payload)
                    except _json.JSONDecodeError:
                        data = {}
                    data["conversation_id"] = conversation_id
                    event = f"event: intent\ndata: {_json.dumps(data, ensure_ascii=False)}\n\n"
                first_event = False
            yield event
            self._collect_event(event, collected)

        # Save assistant message to history
        data_json = ""
        if collected["data_markdown"]:
            try:
                data_json = _json.dumps(
                    {"markdown": collected["data_markdown"]}, ensure_ascii=False
                )
            except (TypeError, ValueError):
                pass

        await self.history.add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=collected["explanation"] or collected["error"],
            intent=collected["intent"],
            sql=collected["sql"],
            data_json=data_json,
        )

    def _collect_event(self, event: str, collected: dict) -> None:
        """从 SSE 事件中提取字段到 collected dict。"""
        import json as _json

        if not event.startswith("event: ") or event.startswith("event: done\n"):
            return

        lines = event.strip().split("\n")
        event_type = ""
        data_str = ""
        for line in lines:
            if line.startswith("event: "):
                event_type = line[7:]
            elif line.startswith("data: "):
                data_str = line[6:]

        if not data_str:
            return

        try:
            payload = _json.loads(data_str)
        except _json.JSONDecodeError:
            return

        if event_type == "intent":
            collected["intent"] = payload.get("intent", "")
        elif event_type == "sql":
            collected["sql"] = payload.get("sql", "")
        elif event_type == "data":
            collected["data_markdown"] = payload.get("markdown", "")
        elif event_type == "explanation":
            collected["explanation"] = payload.get("text", "")
        elif event_type == "error":
            collected["error"] = payload.get("error", "")
```

- [ ] **Step 2: Add SSE endpoint to chat router**

In `backend/routers/chat.py`, add after the `chat()` function:

```python
from sse_starlette.sse import EventSourceResponse


class StreamChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="用户自然语言输入")
    database: str = Field(default="", description="目标数据库配置名")
    conversation_id: Optional[str] = Field(default=None, description="对话 ID，空则创建新对话")


@router.post("/chat/stream")
async def chat_stream(request: StreamChatRequest):
    """流式对话（SSE），逐事件推送 intent → sql → data → explanation → done."""
    if _chat_service is None:
        raise AppError(
            code="SERVICE_NOT_READY",
            message="Chat service has not been initialized.",
            status_code=503,
        )

    generator = _chat_service.process_message_stream(
        message=request.message,
        database=request.database,
        conversation_id=request.conversation_id,
    )
    return EventSourceResponse(generator)
```

Also add the import at top:
```python
from sse_starlette.sse import EventSourceResponse
```

- [ ] **Step 3: Verify import is available**

```bash
cd /Users/apple/Documents/AI/Claude/20260701/sap-b1-db-agent && python -c "from sse_starlette.sse import EventSourceResponse; print('OK')"
```

Expected: `OK` (sse-starlette was already added as a dependency in Phase 1)

- [ ] **Step 4: Add test for SSE endpoint**

Add to `tests/test_chat_router.py`:

```python
class StreamChatRequest:
    """Test helper — matches the Pydantic model."""
    def __init__(self, message, database="", conversation_id=None):
        self.message = message
        self.database = database
        self.conversation_id = conversation_id


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
```

- [ ] **Step 5: Run tests**

```bash
cd /Users/apple/Documents/AI/Claude/20260701/sap-b1-db-agent && python -m pytest tests/ -x -q
```

Expected: all 105+ tests pass

- [ ] **Step 6: Commit**

```bash
git add backend/services/chat_service.py backend/routers/chat.py tests/test_chat_router.py
git commit -m "feat(backend): add SSE streaming chat endpoint /api/chat/stream"
```

---

### Task 3: Add `/api/verify` endpoint

**Files:**
- Create: `backend/routers/verification.py`
- Modify: `backend/main.py`

**Interfaces:**
- Consumes: `ChatService` (already injected in main.py)
- Produces: `POST /api/verify` — standalone verification endpoint

- [ ] **Step 1: Create verification router**

Create `backend/routers/verification.py`:

```python
"""数据验证 API."""
from __future__ import annotations

import logging
from typing import Optional, Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from agent.verifier import VerificationReport, VerificationFinding

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["verify"])


class VerifyRequest(BaseModel):
    database: str = Field(default="", description="目标数据库配置名")


class VerifyFindingItem(BaseModel):
    check_name: str
    status: str  # pass | fail | error
    detail: str


class VerifyResponse(BaseModel):
    plan_name: str
    total_checks: int
    passed: int
    failed: int
    pass_rate: float
    findings: list[VerifyFindingItem]


@router.post("/verify", response_model=VerifyResponse)
def run_verification(request: VerifyRequest) -> VerifyResponse:
    """执行数据验证检查（库存一致性等）。"""
    from config.loader import load_config
    from database.connector import create_connection, close_connection
    from database.executor import execute_query
    from agent.verifier import generate_standard_inventory_checks

    checks = generate_standard_inventory_checks()

    config_path = _get_config_path()
    config = load_config(config_path)

    db_name = request.database or config.agent.default_db
    db_config = config.databases.get(db_name)

    if not db_config:
        return VerifyResponse(
            plan_name="数据验证",
            total_checks=len(checks),
            passed=0,
            failed=0,
            pass_rate=0.0,
            findings=[
                VerifyFindingItem(
                    check_name=c.name,
                    status="error",
                    detail=f"数据库 '{db_name}' 未配置",
                )
                for c in checks
            ],
        )

    findings = []
    conn = create_connection(db_config)
    try:
        for check in checks:
            try:
                result = execute_query(conn, check.check_sql)
                if not result.success:
                    findings.append(VerifyFindingItem(
                        check_name=check.name,
                        status="error",
                        detail=f"执行失败: {result.error}",
                    ))
                elif result.row_count == 0:
                    findings.append(VerifyFindingItem(
                        check_name=check.name,
                        status="pass",
                        detail="检查通过，未发现异常",
                    ))
                else:
                    findings.append(VerifyFindingItem(
                        check_name=check.name,
                        status="fail",
                        detail=f"发现 {result.row_count} 条异常数据",
                    ))
            except Exception as e:
                findings.append(VerifyFindingItem(
                    check_name=check.name,
                    status="error",
                    detail=f"执行异常: {str(e)}",
                ))
    finally:
        close_connection(conn)

    total = len(findings)
    passed = sum(1 for f in findings if f.status == "pass")
    failed = sum(1 for f in findings if f.status in ("fail", "error"))

    return VerifyResponse(
        plan_name="数据验证",
        total_checks=total,
        passed=passed,
        failed=failed,
        pass_rate=passed / total if total > 0 else 0.0,
        findings=findings,
    )


def _get_config_path() -> str:
    import os
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "config", "config.yaml",
    )
```

- [ ] **Step 2: Register router in main.py**

In `backend/main.py`, add:
```python
from backend.routers import verification
```
after the existing router imports (line 16).

And add:
```python
app.include_router(verification.router)
```
after the existing `app.include_router(schema.router)` line.

- [ ] **Step 3: Add test for verify endpoint**

Create `tests/test_verify_router.py`:

```python
"""Tests for /api/verify endpoint."""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def verify_client():
    """Create a TestClient with only the verify router."""
    from fastapi import FastAPI
    from backend.routers.verification import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_verify_returns_findings(verify_client):
    """POST /api/verify should return findings list even without DB."""
    response = verify_client.post("/api/verify", json={"database": "nonexistent"})
    assert response.status_code == 200
    data = response.json()
    assert "findings" in data
    assert "total_checks" in data
    assert data["total_checks"] > 0


def test_verify_response_structure(verify_client):
    """Verify response has expected fields."""
    response = verify_client.post("/api/verify", json={"database": "nonexistent"})
    data = response.json()
    assert "plan_name" in data
    assert "total_checks" in data
    assert "passed" in data
    assert "failed" in data
    assert "pass_rate" in data
    for finding in data["findings"]:
        assert "check_name" in finding
        assert "status" in finding
        assert "detail" in finding
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/apple/Documents/AI/Claude/20260701/sap-b1-db-agent && python -m pytest tests/test_verify_router.py tests/ -x -q
```

Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add backend/routers/verification.py backend/main.py tests/test_verify_router.py
git commit -m "feat(backend): add /api/verify endpoint for data verification checks"
```

---

### Task 4: Add SSE streaming client to frontend API layer

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/client.ts`

**Interfaces:**
- Consumes: `/api/chat/stream` SSE endpoint from Task 2
- Produces: `streamChatMessage(req, callbacks) -> AbortController` for SSE streaming

- [ ] **Step 1: Add SSE event types**

In `frontend/src/api/types.ts`, add after existing types:

```typescript
/** SSE 流式事件类型 */
export interface SSEIntentEvent {
  intent: string
  confidence: number
  conversation_id: string
}

export interface SSESqlEvent {
  sql: string
}

export interface SSEDataEvent {
  markdown?: string
  findings?: VerifyFindingItem[]
  pass_rate?: number
  total?: number
  passed?: number
  failed?: number
}

export interface SSEExplanationEvent {
  text: string
}

export interface SSEErrorEvent {
  error: string
}

export interface VerifyFindingItem {
  check_name: string
  status: string
  detail: string
}

/** 流式回调 */
export interface StreamCallbacks {
  onIntent?: (event: SSEIntentEvent) => void
  onSql?: (event: SSESqlEvent) => void
  onData?: (event: SSEDataEvent) => void
  onExplanation?: (event: SSEExplanationEvent) => void
  onError?: (event: SSEErrorEvent) => void
  onDone?: () => void
}

/** /api/verify 响应 */
export interface VerifyResponse {
  plan_name: string
  total_checks: number
  passed: number
  failed: number
  pass_rate: number
  findings: VerifyFindingItem[]
}
```

- [ ] **Step 2: Add SSE and verify API functions**

In `frontend/src/api/client.ts`, add after `listTables()`:

```typescript
import type {
  // ... existing imports remain
  StreamCallbacks,
  VerifyResponse,
} from './types'

export function streamChatMessage(
  req: ChatRequest,
  callbacks: StreamCallbacks,
): AbortController {
  const controller = new AbortController()

  fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
    signal: controller.signal,
  }).then(async (response) => {
    if (!response.ok) {
      const err = await response.json().catch(() => ({ error: { message: 'Stream failed' } }))
      callbacks.onError?.({ error: err?.error?.message || err?.detail || '流式请求失败' })
      return
    }

    const reader = response.body?.getReader()
    if (!reader) return

    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      let eventType = ''
      let dataStr = ''

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          eventType = line.slice(7).trim()
        } else if (line.startsWith('data: ')) {
          dataStr = line.slice(6)
          this._dispatchSSE(eventType, dataStr, callbacks)
          eventType = ''
          dataStr = ''
        }
      }
    }
  }).catch((err: Error) => {
    if (err.name !== 'AbortError') {
      callbacks.onError?.({ error: err.message || '网络错误' })
    }
  })

  return controller
}

function _dispatchSSE(eventType: string, dataStr: string, callbacks: StreamCallbacks): void {
  try {
    const data = JSON.parse(dataStr)
    switch (eventType) {
      case 'intent':
        callbacks.onIntent?.(data)
        break
      case 'sql':
        callbacks.onSql?.(data)
        break
      case 'data':
        callbacks.onData?.(data)
        break
      case 'explanation':
        callbacks.onExplanation?.(data)
        break
      case 'error':
        callbacks.onError?.(data)
        break
      case 'done':
        callbacks.onDone?.()
        break
    }
  } catch {
    // ignore parse errors for non-JSON data
  }
}

export async function runVerification(database: string): Promise<VerifyResponse> {
  const { data } = await api.post<VerifyResponse>('/verify', { database })
  return data
}
```

Wait — `_dispatchSSE` is defined as a standalone function but `this._dispatchSSE` is called in the Promise chain. Let me fix this:

Instead of `this._dispatchSSE`, just call `_dispatchSSE` directly:

```typescript
          _dispatchSSE(eventType, dataStr, callbacks)
```

- [ ] **Step 3: Verify TypeScript compilation**

```bash
cd /Users/apple/Documents/AI/Claude/20260701/sap-b1-db-agent/frontend && npx vue-tsc --noEmit
```

Expected: no type errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/client.ts
git commit -m "feat(frontend): add SSE streaming client and /api/verify client"
```

---

### Task 5: Update chat store to support streaming messages

**Files:**
- Modify: `frontend/src/stores/chat.ts`

**Interfaces:**
- Consumes: `streamChatMessage()` from Task 4
- Produces: `sendMessageStream()` action that progressively updates a DisplayMessage

- [ ] **Step 1: Add `sendMessageStream()` to chat store**

In `frontend/src/stores/chat.ts`, add `sendMessageStream` function:

```typescript
import { sendChatMessage, streamChatMessage, listConversations, getConversation, deleteConversation } from '../api/client'
import type { SSEIntentEvent, SSESqlEvent, SSEDataEvent, SSEExplanationEvent, SSEErrorEvent } from '../api/types'
```

In the store return object, add `sendMessageStream`:

```typescript
  let _abortController: AbortController | null = null

  async function sendMessageStream(content: string, database: string) {
    // Abort any previous stream
    if (_abortController) {
      _abortController.abort()
    }

    // Add user message immediately
    const userMsg: DisplayMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
      intent: '',
      sql: '',
      dataMarkdown: '',
      explanation: '',
      timestamp: new Date(),
    }
    messages.value.push(userMsg)
    isLoading.value = true
    error.value = null

    // Create placeholder assistant message
    const assistantId = crypto.randomUUID()
    const assistantMsg: DisplayMessage = {
      id: assistantId,
      role: 'assistant',
      content: '思考中...',
      intent: '',
      sql: '',
      dataMarkdown: '',
      explanation: '',
      timestamp: new Date(),
    }
    messages.value.push(assistantMsg)

    _abortController = streamChatMessage(
      { message: content, database, conversation_id: activeConversationId.value },
      {
        onIntent: (event: SSEIntentEvent) => {
          updateAssistant(assistantId, {
            intent: event.intent,
            content: `识别意图: ${event.intent}`,
          })
          if (!activeConversationId.value) {
            activeConversationId.value = event.conversation_id
            fetchConversations(database)
          }
        },
        onSql: (event: SSESqlEvent) => {
          updateAssistant(assistantId, {
            sql: event.sql,
            content: `正在执行 SQL...`,
          })
        },
        onData: (event: SSEDataEvent) => {
          const md = event.markdown || ''
          updateAssistant(assistantId, {
            dataMarkdown: md,
            content: md ? '查询结果已返回' : '处理中...',
          })
        },
        onExplanation: (event: SSEExplanationEvent) => {
          updateAssistant(assistantId, {
            explanation: event.text,
            content: event.text,
          })
        },
        onError: (event: SSEErrorEvent) => {
          updateAssistant(assistantId, {
            content: event.error,
          })
          error.value = event.error
        },
        onDone: () => {
          isLoading.value = false
          _abortController = null
        },
      },
    )
  }

  function updateAssistant(id: string, updates: Partial<DisplayMessage>) {
    const idx = messages.value.findIndex(m => m.id === id)
    if (idx !== -1) {
      messages.value[idx] = { ...messages.value[idx], ...updates }
    }
  }
```

Add these to the return statement:
```typescript
    sendMessageStream,
```

- [ ] **Step 2: Verify TypeScript compilation**

```bash
cd /Users/apple/Documents/AI/Claude/20260701/sap-b1-db-agent/frontend && npx vue-tsc --noEmit
```

Expected: no type errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/stores/chat.ts
git commit -m "feat(frontend): add streaming sendMessage support to chat store"
```

---

### Task 6: Wire streaming into ChatView and update ChatMessage component

**Files:**
- Modify: `frontend/src/views/ChatView.vue`
- Modify: `frontend/src/components/ChatMessage.vue`

**Interfaces:**
- Consumes: `chatStore.sendMessageStream()` from Task 5

- [ ] **Step 1: Update ChatView to use streaming**

In `frontend/src/views/ChatView.vue`, change the `onSend` function:

```typescript
function onSend(message: string) {
  chatStore.sendMessageStream(message, settingsStore.activeDatabase)
}
```

(was `chatStore.sendMessage(...)`, now `chatStore.sendMessageStream(...)`)

- [ ] **Step 2: Update ChatMessage.vue to handle loading state**

Read the current ChatMessage.vue first, then update. The current component likely shows static content. We need it to handle the "思考中..." loading indicator gracefully.

In `frontend/src/components/ChatMessage.vue`, ensure the template handles partial messages:

The key is that the streaming message progressively updates — intent → sql → data → explanation. The ChatMessage component already renders `intent`, `sql`, `dataMarkdown`, and `explanation` separately (via IntentBadge, SqlBlock, DataTable, Explanation sub-components). Since we're mutating the message object in place (via reactive refs), Vue's reactivity should automatically update the rendered output.

No structural change needed to ChatMessage.vue — just verify the sub-components handle empty/partial data gracefully (they should, since they were built to handle optional props).

- [ ] **Step 3: Verify TypeScript + build**

```bash
cd /Users/apple/Documents/AI/Claude/20260701/sap-b1-db-agent/frontend && npx vue-tsc --noEmit && npm run build
```

Expected: no type errors, dist/ produced

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/ChatView.vue
git commit -m "feat(frontend): wire streaming sendMessage into ChatView"
```

---

### Task 7: Build VerifyView page and VerifyCard component

**Files:**
- Create: `frontend/src/components/VerifyCard.vue`
- Modify: `frontend/src/views/VerifyView.vue`

**Interfaces:**
- Consumes: `runVerification()` from Task 4 (api/client.ts)

- [ ] **Step 1: Create VerifyCard component**

Create `frontend/src/components/VerifyCard.vue`:

```vue
<script setup lang="ts">
import type { VerifyFindingItem } from '../api/types'

const props = defineProps<{
  finding: VerifyFindingItem
}>()

const statusConfig: Record<string, { type: 'success' | 'error' | 'warning'; icon: string; label: string }> = {
  pass: { type: 'success', icon: '✅', label: '通过' },
  fail: { type: 'error', icon: '❌', label: '异常' },
  error: { type: 'warning', icon: '⚠️', label: '错误' },
}
const config = statusConfig[props.finding.status] || statusConfig.error
</script>

<template>
  <n-card :bordered="true" size="small" class="verify-card">
    <template #header>
      <div class="card-header">
        <span class="icon">{{ config.icon }}</span>
        <span class="name">{{ finding.check_name }}</span>
        <n-tag :type="config.type" size="small">{{ config.label }}</n-tag>
      </div>
    </template>
    <p class="detail">{{ finding.detail }}</p>
  </n-card>
</template>

<style scoped>
.verify-card {
  margin-bottom: 12px;
}
.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
}
.icon {
  font-size: 18px;
}
.name {
  flex: 1;
  font-weight: 500;
}
.detail {
  color: #666;
  margin: 0;
  font-size: 14px;
}
</style>
```

- [ ] **Step 2: Build VerifyView page**

Replace `frontend/src/views/VerifyView.vue`:

```vue
<script setup lang="ts">
import { ref } from 'vue'
import { runVerification } from '../api/client'
import { useSettingsStore } from '../stores/settings'
import type { VerifyResponse, VerifyFindingItem } from '../api/types'
import VerifyCard from '../components/VerifyCard.vue'

const settingsStore = useSettingsStore()
const isLoading = ref(false)
const result = ref<VerifyResponse | null>(null)
const error = ref<string | null>(null)

async function onRunVerify() {
  isLoading.value = true
  error.value = null
  result.value = null
  try {
    result.value = await runVerification(settingsStore.activeDatabase)
  } catch (e: any) {
    error.value = e?.message || '验证失败'
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div class="verify-view">
    <div class="verify-content">
      <n-space vertical size="large" style="max-width: 800px; padding: 24px;">
        <n-card title="数据校验">
          <template #header-extra>
            <n-button
              type="primary"
              :loading="isLoading"
              @click="onRunVerify"
            >
              执行全部校验
            </n-button>
          </template>

          <n-space vertical>
            <n-text depth="3">
              当前数据库: <n-tag type="info" size="small">{{ settingsStore.activeDatabase }}</n-tag>
            </n-text>

            <n-alert v-if="error" type="error" :title="error" closable />

            <div v-if="result" class="result-summary">
              <n-space align="center">
                <n-statistic label="总检查项" :value="result.total_checks" />
                <n-statistic label="通过">
                  <span class="stat-pass">{{ result.passed }}</span>
                </n-statistic>
                <n-statistic label="异常">
                  <span class="stat-fail">{{ result.failed }}</span>
                </n-statistic>
                <n-statistic label="通过率">
                  <span :class="result.pass_rate >= 0.8 ? 'stat-pass' : 'stat-fail'">
                    {{ (result.pass_rate * 100).toFixed(0) }}%
                  </span>
                </n-statistic>
              </n-space>
            </div>

            <div v-if="result">
              <VerifyCard
                v-for="finding in result.findings"
                :key="finding.check_name"
                :finding="finding"
              />
            </div>

            <n-empty
              v-if="!result && !error"
              description="点击「执行全部校验」开始数据验证"
            />
          </n-space>
        </n-card>
      </n-space>
    </div>
  </div>
</template>

<style scoped>
.verify-view {
  height: calc(100vh - 52px);
  overflow-y: auto;
}
.verify-content {
  display: flex;
  justify-content: center;
}
.result-summary {
  margin-bottom: 16px;
  padding: 16px;
  background: #f5f7fa;
  border-radius: 8px;
}
.stat-pass { color: #18a058; font-weight: 600; }
.stat-fail { color: #d03050; font-weight: 600; }
</style>
```

- [ ] **Step 3: Verify TypeScript + build**

```bash
cd /Users/apple/Documents/AI/Claude/20260701/sap-b1-db-agent/frontend && npx vue-tsc --noEmit && npm run build
```

Expected: no type errors, dist/ produced

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/VerifyCard.vue frontend/src/views/VerifyView.vue
git commit -m "feat(frontend): build VerifyView page with verification check cards"
```

---

### Task 8: Enhance SettingsView with verification status and better layout

**Files:**
- Modify: `frontend/src/views/SettingsView.vue`

**Interfaces:**
- Consumes: existing `testConnection()`, `listTables()` from api/client.ts

The SettingsView already has connection test + table list. Enhance it with:
- API status indicator
- Better visual layout with sections
- Connection detail display (host, port)

- [ ] **Step 1: Enhance SettingsView**

Replace `frontend/src/views/SettingsView.vue`:

```vue
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { testConnection, listTables } from '../api/client'
import { useSettingsStore } from '../stores/settings'
import type { TableInfo, ConnectionTestResponse } from '../api/types'

const settingsStore = useSettingsStore()

const connectionStatus = ref<'idle' | 'testing' | 'success' | 'fail'>('idle')
const connectionMessage = ref('')
const connectionDetail = ref<ConnectionTestResponse | null>(null)
const tables = ref<TableInfo[]>([])
const tablesLoading = ref(false)
const apiStatus = ref<'checking' | 'ok' | 'error'>('checking')

onMounted(async () => {
  try {
    const resp = await fetch('/health')
    apiStatus.value = resp.ok ? 'ok' : 'error'
  } catch {
    apiStatus.value = 'error'
  }
})

async function onTestConnection() {
  connectionStatus.value = 'testing'
  connectionDetail.value = null
  try {
    const result = await testConnection({ database: settingsStore.activeDatabase })
    connectionStatus.value = result.success ? 'success' : 'fail'
    connectionMessage.value = result.message
    connectionDetail.value = result
  } catch (e: any) {
    connectionStatus.value = 'fail'
    connectionMessage.value = e?.message || '连接失败'
  }
}

async function onLoadTables() {
  tablesLoading.value = true
  try {
    tables.value = await listTables()
  } finally {
    tablesLoading.value = false
  }
}
</script>

<template>
  <div class="settings-view">
    <n-space vertical size="large" style="max-width: 700px; padding: 24px;">

      <!-- API Status -->
      <n-card title="服务状态">
        <n-space align="center">
          <n-tag v-if="apiStatus === 'ok'" type="success" size="medium">API 正常</n-tag>
          <n-tag v-else-if="apiStatus === 'error'" type="error" size="medium">API 不可用</n-tag>
          <n-tag v-else type="warning" size="medium">检查中...</n-tag>
          <n-text depth="3">目标数据库: {{ settingsStore.activeDatabase }}</n-text>
        </n-space>
      </n-card>

      <!-- Connection Test -->
      <n-card title="数据库连接">
        <n-space vertical>
          <n-space align="center">
            <n-button @click="onTestConnection" :loading="connectionStatus === 'testing'">
              测试连接
            </n-button>
            <n-tag v-if="connectionStatus === 'success'" type="success">已连接</n-tag>
            <n-tag v-else-if="connectionStatus === 'fail'" type="error">连接失败</n-tag>
          </n-space>
          <p v-if="connectionMessage" style="margin: 0; color: #666;">
            {{ connectionMessage }}
          </p>
          <n-descriptions
            v-if="connectionDetail?.success"
            label-placement="left"
            bordered
            :column="2"
            size="small"
          >
            <n-descriptions-item label="数据库">{{ connectionDetail.database }}</n-descriptions-item>
            <n-descriptions-item label="主机">{{ connectionDetail.host }}</n-descriptions-item>
            <n-descriptions-item label="端口">{{ connectionDetail.port }}</n-descriptions-item>
          </n-descriptions>
        </n-space>
      </n-card>

      <!-- Table Schema -->
      <n-card title="表结构">
        <n-space vertical>
          <n-space align="center">
            <n-button @click="onLoadTables" :loading="tablesLoading">加载表列表</n-button>
            <n-text v-if="tables.length" depth="3">共 {{ tables.length }} 张表</n-text>
          </n-space>
          <n-table v-if="tables.length" style="margin-top: 12px;" :bordered="true" :single-line="false" size="small">
            <thead>
              <tr><th>表名</th><th>描述</th><th>字段数</th></tr>
            </thead>
            <tbody>
              <tr v-for="t in tables" :key="t.name">
                <td><n-tag type="info" size="small">{{ t.name }}</n-tag></td>
                <td>{{ t.description || '-' }}</td>
                <td>{{ t.column_count }}</td>
              </tr>
            </tbody>
          </n-table>
        </n-space>
      </n-card>

    </n-space>
  </div>
</template>

<style scoped>
.settings-view {
  height: calc(100vh - 52px);
  overflow-y: auto;
  display: flex;
  justify-content: center;
}
</style>
```

- [ ] **Step 2: Verify TypeScript + build**

```bash
cd /Users/apple/Documents/AI/Claude/20260701/sap-b1-db-agent/frontend && npx vue-tsc --noEmit && npm run build
```

Expected: no type errors, dist/ produced

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/SettingsView.vue
git commit -m "feat(frontend): enhance SettingsView with API status, connection details, improved layout"
```

---

### Task 9: End-to-end verification

**Files:**
- No new files — verification only

- [ ] **Step 1: Run all backend tests**

```bash
cd /Users/apple/Documents/AI/Claude/20260701/sap-b1-db-agent && python -m pytest tests/ -v
```

Expected: all tests pass (should be ~107+)

- [ ] **Step 2: Verify frontend builds clean**

```bash
cd /Users/apple/Documents/AI/Claude/20260701/sap-b1-db-agent/frontend && npx vue-tsc --noEmit && npm run build
```

Expected: no type errors, dist/ produced

- [ ] **Step 3: Verify router includes all pages**

Confirm `frontend/src/router/index.ts` already includes routes for `/` (ChatView), `/verify` (VerifyView), `/settings` (SettingsView). These were set up in Phase 2.

- [ ] **Step 4: Update progress.md**

```bash
echo "Phase3 Task 1: complete (agent process_stream() SSE generator)" >> .superpowers/sdd/progress.md
echo "Phase3 Task 2: complete (/api/chat/stream endpoint)" >> .superpowers/sdd/progress.md
echo "Phase3 Task 3: complete (/api/verify endpoint)" >> .superpowers/sdd/progress.md
echo "Phase3 Task 4: complete (frontend SSE client + verify API)" >> .superpowers/sdd/progress.md
echo "Phase3 Task 5: complete (chat store streaming support)" >> .superpowers/sdd/progress.md
echo "Phase3 Task 6: complete (ChatView streaming wire-up)" >> .superpowers/sdd/progress.md
echo "Phase3 Task 7: complete (VerifyView + VerifyCard)" >> .superpowers/sdd/progress.md
echo "Phase3 Task 8: complete (SettingsView enhancements)" >> .superpowers/sdd/progress.md
echo "Phase3 Task 9: E2E verified — all tests pass, frontend builds clean" >> .superpowers/sdd/progress.md
```

- [ ] **Step 5: Commit progress**

```bash
git add .superpowers/sdd/progress.md
git commit -m "docs: update progress — Phase 3 complete"
```
