"""Tests for DBAgent.process_stream() async generator."""
import json
import pytest
from unittest.mock import MagicMock
from agent.core import DBAgent


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

    # First event should be intent dict
    assert isinstance(events[0], dict)
    assert events[0]["event"] == "intent"
    data = json.loads(events[0]["data"])
    assert data["intent"] == "chat"

    # Last event should be done dict
    assert isinstance(events[-1], dict)
    assert events[-1]["event"] == "done"


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
    event_types = [e["event"] for e in events if isinstance(e, dict)]
    assert "intent" in event_types
    assert "explanation" in event_types
    assert "done" in event_types
