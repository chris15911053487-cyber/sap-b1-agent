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
