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
