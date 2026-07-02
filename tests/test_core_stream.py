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
