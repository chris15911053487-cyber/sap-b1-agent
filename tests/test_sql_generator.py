# tests/test_sql_generator.py
import pytest
from unittest.mock import patch, MagicMock
from agent.sql_generator import (
    SqlGenerationResult,
    build_schema_context_prompt,
    build_sql_generation_prompt,
)
from database.schema import SchemaCache, get_core_tables


class TestBuildSchemaContextPrompt:
    def test_includes_key_tables(self):
        tables = get_core_tables()
        prompt = build_schema_context_prompt(tables)

        assert "OITM" in prompt
        assert "ORDR" in prompt
        assert "物料主数据" in prompt
        assert "销售订单" in prompt

    def test_formats_table_structure(self):
        tables = get_core_tables()
        prompt = build_schema_context_prompt(tables)
        # 应该包含列信息
        assert "ItemCode" in prompt
        assert "ItemName" in prompt


class TestBuildSqlGenerationPrompt:
    def test_includes_user_question(self):
        prompt = build_sql_generation_prompt(
            user_input="查一下物料A001的库存",
            schema_context="[Schema Context]",
        )
        assert "物料A001的库存" in prompt
        assert "[Schema Context]" in prompt

    def test_includes_sap_b1_rules(self):
        prompt = build_sql_generation_prompt(
            user_input="查数据",
            schema_context="[Schema]",
        )
        assert "SAP Business One" in prompt
        assert "TOP" in prompt  # 限制返回行数

    def test_includes_sql_server_syntax_hint(self):
        prompt = build_sql_generation_prompt(
            user_input="查数据",
            schema_context="[Schema]",
        )
        assert "SQL Server" in prompt


class TestSqlGenerationResult:
    def test_creates_success_result(self):
        result = SqlGenerationResult(
            sql="SELECT * FROM OITM",
            explanation="查询所有物料",
            success=True,
        )
        assert result.sql == "SELECT * FROM OITM"
        assert result.success is True

    def test_creates_error_result(self):
        result = SqlGenerationResult(
            sql="",
            explanation="",
            success=False,
            error="无法理解查询意图",
        )
        assert result.success is False
        assert result.error == "无法理解查询意图"
