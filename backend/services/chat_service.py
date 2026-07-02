"""聊天服务 — 封装 DBAgent，管理对话生命周期."""
from __future__ import annotations

import asyncio
import copy
import json
import logging
from dataclasses import dataclass
from typing import Optional

from agent.core import DBAgent, AgentResponse
from config.loader import load_config
from backend.middleware.error_handler import AppError
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

        # Load conversation history for multi-turn context
        history_messages: list[dict] = []
        if conversation_id:
            conv = await self.history.get_conversation(conversation_id)
            if conv and conv.get("messages"):
                history_messages = [
                    {
                        "role": m["role"],
                        "content": m["content"],
                        "sql": m.get("sql", ""),
                        "intent": m.get("intent", ""),
                    }
                    for m in conv["messages"]
                ]

        # Create agent — override default_db if database specified
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
            # Deep copy to avoid mutating the shared config object
            agent.config = copy.deepcopy(agent.config)
            agent.config.agent.default_db = database

        # Process with existing DBAgent
        try:
            agent_response: AgentResponse = await asyncio.to_thread(
                agent.process, message, False, history_messages
            )
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

        # Load conversation history for multi-turn context
        history_messages: list[dict] = []
        if conversation_id:
            conv = await self.history.get_conversation(conversation_id)
            if conv and conv.get("messages"):
                history_messages = [
                    {
                        "role": m["role"],
                        "content": m["content"],
                        "sql": m.get("sql", ""),
                        "intent": m.get("intent", ""),
                    }
                    for m in conv["messages"]
                ]

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
        try:
            async for event in agent.process_stream(message, history=history_messages):
                if first_event:
                    if event.startswith("event: intent\n"):
                        prefix = "event: intent\ndata: "
                        payload = event[len(prefix):].strip()
                        try:
                            data = json.loads(payload)
                        except json.JSONDecodeError:
                            data = {}
                        data["conversation_id"] = conversation_id
                        event = f"event: intent\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                    first_event = False
                yield event
                self._collect_event(event, collected)
        except Exception as e:
            logger.exception(f"Stream processing failed: {e}")
            error_event = f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
            yield error_event
            collected["error"] = str(e)

        # Save assistant message to history
        data_json = ""
        if collected["data_markdown"]:
            try:
                data_json = json.dumps(
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
        if not event.startswith("event: "):
            return
        if event.startswith("event: done\n"):
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
            payload = json.loads(data_str)
        except json.JSONDecodeError:
            return

        if event_type == "intent":
            collected["intent"] = payload.get("intent", "")
        elif event_type == "sql":
            collected["sql"] = payload.get("sql", "")
        elif event_type == "data":
            # Capture query results (markdown) or verification findings
            if "markdown" in payload:
                collected["data_markdown"] = payload.get("markdown", "")
            elif "findings" in payload:
                collected["data_markdown"] = json.dumps(payload, ensure_ascii=False)
        elif event_type == "explanation":
            collected["explanation"] = payload.get("text", "")
        elif event_type == "error":
            collected["error"] = payload.get("error", "")
