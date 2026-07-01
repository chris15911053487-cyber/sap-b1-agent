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
