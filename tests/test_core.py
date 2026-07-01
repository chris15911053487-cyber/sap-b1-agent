# tests/test_core.py
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from agent.core import DBAgent, AgentResponse
from config.loader import AppConfig, AgentConfig


@pytest.fixture
def app_config():
    return AppConfig(
        databases={},
        agent=AgentConfig(
            default_db="test",
            model="deepseek-chat",
            max_query_rows=100,
            log_level="DEBUG",
            locale="zh_CN",
        ),
    )


@pytest.fixture
def agent(app_config):
    return DBAgent(config=app_config, api_key="test-key")


class TestDBAgent:
    def test_initializes_with_config(self, agent, app_config):
        assert agent.config == app_config
        assert agent.api_key == "test-key"
        assert agent.schema_cache is not None

    def test_loads_core_tables_on_init(self, agent):
        assert agent.schema_cache.has("OITM")
        assert agent.schema_cache.has("ORDR")

    def test_process_hello_returns_chat(self, agent):
        response = agent.process("你好")
        assert isinstance(response, AgentResponse)
        assert response.intent == "chat"
        assert response.success is True

    @patch("agent.core.DBAgent._handle_query")
    def test_process_query_routes_correctly(self, mock_query, agent):
        mock_query.return_value = AgentResponse(
            intent="query",
            sql="SELECT TOP 10 * FROM OITM",
            data_table="| ItemCode |\n| A001 |",
            explanation="查询成功",
            success=True,
        )
        response = agent.process("查一下所有物料")
        assert response.intent == "query"
        mock_query.assert_called_once()

    @patch("agent.core.DBAgent._handle_build_sp")
    def test_process_sp_request_routes_correctly(self, mock_sp, agent):
        mock_sp.return_value = AgentResponse(
            intent="build_sp",
            sql="CREATE PROCEDURE SP_Test...",
            explanation="SP设计完成",
            success=True,
        )
        response = agent.process("创建一个库存盘点的存储过程")
        assert response.intent == "build_sp"

    @patch("agent.core.DBAgent._handle_verify")
    def test_process_verify_routes_correctly(self, mock_verify, agent):
        mock_verify.return_value = AgentResponse(
            intent="verify",
            explanation="验证完成: 4/4 通过",
            success=True,
        )
        response = agent.process("验证一下库存数据")
        assert response.intent == "verify"


class TestAgentResponse:
    def test_creates_success_response(self):
        resp = AgentResponse(
            intent="query",
            sql="SELECT 1",
            data_table="table",
            explanation="OK",
            success=True,
        )
        assert resp.success is True

    def test_creates_error_response(self):
        resp = AgentResponse(
            intent="query",
            success=False,
            error="Connection timeout",
        )
        assert resp.success is False
        assert resp.error == "Connection timeout"
