# tests/test_interpreter.py
import pytest
from agent.interpreter import (
    format_result_as_markdown_table,
    build_interpretation_prompt,
)


class TestFormatResultAsMarkdownTable:
    def test_formats_single_row(self):
        result = type("QueryResult", (), {
            "columns": ["ItemCode", "ItemName", "OnHand"],
            "rows": [("A001", "Widget", 100)],
            "row_count": 1,
            "success": True,
        })
        table = format_result_as_markdown_table(result)
        assert "ItemCode" in table
        assert "A001" in table
        assert "Widget" in table
        assert "100" in table

    def test_formats_multiple_rows(self):
        result = type("QueryResult", (), {
            "columns": ["CardCode", "CardName"],
            "rows": [("C001", "客户A"), ("C002", "客户B")],
            "row_count": 2,
            "success": True,
        })
        table = format_result_as_markdown_table(result)
        assert table.count("\n") >= 3  # 表头 + 分隔行 + 2数据行

    def test_handles_empty_result(self):
        result = type("QueryResult", (), {
            "columns": [],
            "rows": [],
            "row_count": 0,
            "success": True,
        })
        table = format_result_as_markdown_table(result)
        assert "没有数据" in table


class TestBuildInterpretationPrompt:
    def test_includes_question_and_data(self):
        result = type("QueryResult", (), {
            "columns": ["TotalAmount"],
            "rows": [(150000,)],
            "row_count": 1,
            "success": True,
        })
        table = format_result_as_markdown_table(result)
        prompt = build_interpretation_prompt("上月销售额", table)
        assert "上月销售额" in prompt
        assert "150000" in prompt

    def test_includes_request_for_insights(self):
        prompt = build_interpretation_prompt("查询", "data_table")
        assert "解读" in prompt
        assert "分析" in prompt
