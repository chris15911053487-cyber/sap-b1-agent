"""Tests for IM webhook endpoints."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def webhook_client():
    from fastapi import FastAPI
    from backend.routers.webhook import router
    import backend.routers.chat as chat_mod
    from unittest.mock import AsyncMock, MagicMock

    app = FastAPI()
    app.include_router(router)

    # Mock chat service for webhook processing
    mock_svc = MagicMock()
    async def mock_process(message, database="", conversation_id=None):
        from backend.services.chat_service import ChatResponse
        return ChatResponse(
            intent="chat",
            explanation=f"回复: {message}",
            conversation_id="test-conv-id",
            success=True,
        )
    mock_svc.process_message = mock_process
    chat_mod._chat_service = mock_svc

    return TestClient(app)


def test_feishu_url_verification(webhook_client):
    """Feishu should return challenge for URL verification."""
    response = webhook_client.post("/api/webhook/feishu", json={
        "type": "url_verification",
        "challenge": "test-challenge-123",
        "token": "test-token",
    })
    assert response.status_code == 200
    assert response.json()["challenge"] == "test-challenge-123"


def test_feishu_message(webhook_client):
    """Feishu should process messages and return card."""
    response = webhook_client.post("/api/webhook/feishu", json={
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "message": {"content": '{"text":"查库存"}'},
            "sender": {"sender_id": {"user_id": "user123"}},
        },
    })
    assert response.status_code == 200
    data = response.json()
    assert data["msg_type"] == "interactive"
    assert "card" in data


def test_wecom_message(webhook_client):
    """WeCom should process text messages."""
    response = webhook_client.post("/api/webhook/wecom", json={
        "msgtype": "text",
        "text": {"content": "查销售订单"},
        "from": {"userid": "user456", "name": "张三"},
    })
    assert response.status_code == 200
    data = response.json()
    assert data["msgtype"] == "markdown"


def test_dingtalk_empty_message(webhook_client):
    """DingTalk should handle empty messages gracefully."""
    response = webhook_client.post("/api/webhook/dingtalk", json={
        "msgtype": "text",
        "text": {"content": ""},
    })
    assert response.status_code == 200
