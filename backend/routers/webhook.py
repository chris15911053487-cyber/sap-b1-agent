"""IM 机器人 Webhook 端点 — 飞书 / 企微 / 钉钉."""
from __future__ import annotations

import json
import logging
import time
from typing import Optional, Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/webhook", tags=["webhook"])

logger = logging.getLogger(__name__)

_MAX_REPLY_LENGTH = 4000
_BOT_NAME = "SAP B1 智能助手"
_WEBHOOK_TIMEOUT = 10

# ============================================================
# Shared models
# ============================================================

class WebhookContext(BaseModel):
    """从 IM 消息中提取的统一上下文."""
    platform: str
    user_id: str = ""
    user_name: str = ""
    message: str
    raw: dict[str, Any] = Field(default_factory=dict)


# ============================================================
# 飞书 (Feishu / Lark)
# ============================================================

@router.post("/feishu")
async def feishu_webhook(request: Request):
    """飞书机器人 Webhook 回调.

    飞书事件订阅格式:
    - URL 验证: {"challenge": "...", "token": "...", "type": "url_verification"}
    - 消息事件: {"schema": "2.0", "header": {"event_type": "im.message.receive_v1"}, "event": {...}}
    """
    body = await request.json()
    logger.info(f"Feishu webhook: type={body.get('type', body.get('header', {}).get('event_type', 'unknown'))}")

    # URL 验证挑战
    if body.get("type") == "url_verification":
        challenge = body.get("challenge", "")
        return {"challenge": challenge}

    # 消息事件处理
    ctx = _parse_feishu_message(body)
    if not ctx or not ctx.message:
        return {"code": 0, "msg": "no message content"}

    reply_text = await _process_with_chat(ctx)
    return _build_feishu_card_reply(reply_text, ctx)


def _parse_feishu_message(body: dict) -> Optional[WebhookContext]:
    """从飞书事件中提取消息文本."""
    try:
        event = body.get("event", {})
        message = event.get("message", {})
        content_str = message.get("content", "{}")
        content = json.loads(content_str) if isinstance(content_str, str) else content_str
        text = content.get("text", "") or content.get("title", "")

        sender = event.get("sender", {})
        return WebhookContext(
            platform="feishu",
            user_id=sender.get("sender_id", {}).get("user_id", ""),
            message=text,
            raw=body,
        )
    except Exception:
        logger.exception("Failed to parse Feishu message")
        return None


def _build_feishu_card_reply(text: str, ctx: WebhookContext) -> dict:
    """构建飞书卡片回复."""
    return {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": _BOT_NAME}},
            "elements": [
                {"tag": "markdown", "content": text[:_MAX_REPLY_LENGTH]},
                {"tag": "hr"},
                {"tag": "note", "elements": [
                    {"tag": "plain_text", "content": f"查询人: {ctx.user_id or '未知'} | {time.strftime('%Y-%m-%d %H:%M')}"}
                ]},
            ],
        },
    }


# ============================================================
# 企业微信 (WeCom)
# ============================================================

@router.post("/wecom")
async def wecom_webhook(request: Request):
    """企业微信机器人 Webhook 回调.

    企微群机器人消息格式:
    {
      "msgtype": "text",
      "text": {"content": "用户消息"},
      "from": {"userid": "...", "name": "..."},
      "webhook_url": "..."  # 回复用
    }
    验证: GET 请求带 msg_signature/timestamp/nonce/echostr 参数
    """
    # GET 请求 — URL 验证
    if request.method == "GET":
        params = request.query_params
        echostr = params.get("echostr", "")
        # 生产环境应验证 msg_signature
        return int(echostr) if echostr.isdigit() else echostr

    body = await request.json()
    logger.info(f"WeCom webhook: msgtype={body.get('msgtype', 'unknown')}")

    ctx = _parse_wecom_message(body)
    if not ctx or not ctx.message:
        return {"errcode": 0, "errmsg": "ok"}

    reply_text = await _process_with_chat(ctx)

    # 如果有 webhook_url，主动推送回复
    webhook_url = body.get("webhook_url", "")
    if webhook_url:
        await _send_wecom_reply(webhook_url, reply_text)

    return _build_wecom_reply(reply_text)


def _parse_wecom_message(body: dict) -> Optional[WebhookContext]:
    """从企微消息中提取文本."""
    try:
        text_obj = body.get("text", {})
        text = text_obj.get("content", "")
        from_user = body.get("from", {})
        return WebhookContext(
            platform="wecom",
            user_id=from_user.get("userid", ""),
            user_name=from_user.get("name", ""),
            message=text,
            raw=body,
        )
    except Exception:
        logger.exception("Failed to parse WeCom message")
        return None


async def _send_wecom_reply(webhook_url: str, text: str):
    """通过企微 webhook URL 推送回复."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=_WEBHOOK_TIMEOUT) as client:
            await client.post(webhook_url, json={
                "msgtype": "markdown",
                "markdown": {"content": f"## {_BOT_NAME}\n{text[:_MAX_REPLY_LENGTH]}"},
            })
    except Exception:
        logger.exception("Failed to send WeCom webhook reply")


def _build_wecom_reply(text: str) -> dict:
    """构建企微同步回复."""
    return {
        "msgtype": "markdown",
        "markdown": {"content": f"## {_BOT_NAME}\n{text[:_MAX_REPLY_LENGTH]}"},
    }


# ============================================================
# 钉钉 (DingTalk)
# ============================================================

@router.post("/dingtalk")
async def dingtalk_webhook(request: Request):
    """钉钉机器人 Webhook 回调.

    钉钉 Outgoing Webhook 格式:
    {
      "msgtype": "text",
      "text": {"content": "用户消息"},
      "senderId": "...",
      "senderNick": "...",
      "sessionWebhook": "..."  # 回复地址
    }
    """
    body = await request.json()
    logger.info(f"DingTalk webhook: msgtype={body.get('msgtype', 'unknown')}")

    ctx = _parse_dingtalk_message(body)
    if not ctx or not ctx.message:
        return {"errcode": 0, "errmsg": "ok"}

    reply_text = await _process_with_chat(ctx)

    # 如果提供了 sessionWebhook，主动推送回复
    session_webhook = body.get("sessionWebhook", "")
    if session_webhook:
        await _send_dingtalk_reply(session_webhook, reply_text)

    return _build_dingtalk_reply(reply_text)


def _parse_dingtalk_message(body: dict) -> Optional[WebhookContext]:
    """从钉钉消息中提取文本."""
    try:
        text_obj = body.get("text", {})
        text = text_obj.get("content", "")
        return WebhookContext(
            platform="dingtalk",
            user_id=body.get("senderId", ""),
            user_name=body.get("senderNick", ""),
            message=text,
            raw=body,
        )
    except Exception:
        logger.exception("Failed to parse DingTalk message")
        return None


async def _send_dingtalk_reply(webhook_url: str, text: str):
    """通过钉钉 webhook URL 推送回复."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=_WEBHOOK_TIMEOUT) as client:
            await client.post(webhook_url, json={
                "msgtype": "markdown",
                "markdown": {"title": _BOT_NAME, "text": text[:_MAX_REPLY_LENGTH]},
            })
    except Exception:
        logger.exception("Failed to send DingTalk webhook reply")


def _build_dingtalk_reply(text: str) -> dict:
    """构建钉钉同步回复."""
    return {
        "msgtype": "markdown",
        "markdown": {"title": _BOT_NAME, "text": text[:_MAX_REPLY_LENGTH]},
    }


# ============================================================
# Shared chat processing
# ============================================================

async def _process_with_chat(ctx: WebhookContext) -> str:
    """调用 ChatService 处理消息并返回中文解释."""
    import backend.routers.chat as chat_mod

    chat_svc = chat_mod._chat_service
    if chat_svc is None:
        logger.error("ChatService not initialized for webhook")
        return "抱歉，AI 服务尚未就绪，请稍后重试。"

    try:
        result = await chat_svc.process_message(
            message=ctx.message,
            database="",  # 使用默认数据库
        )
        if result.success:
            return result.explanation or "查询已完成，暂无结果。"
        else:
            return f"处理失败: {result.error}"
    except Exception as e:
        logger.exception(f"Webhook chat processing failed: {e}")
        return f"处理出错: {str(e)}"
