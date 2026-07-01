# tests/test_intent.py
import pytest
from agent.intent import Intent, IntentResult, analyze_intent


class TestIntentEnum:
    def test_all_expected_values(self):
        assert Intent.QUERY == "query"
        assert Intent.BUILD_SP == "build_sp"
        assert Intent.VERIFY == "verify"
        assert Intent.CHAT == "chat"


class TestAnalyzeIntent:
    def test_detects_query_intent(self):
        result = analyze_intent("查一下上个月销售订单前10的客户")
        assert result.intent == Intent.QUERY
        assert result.confidence > 0.5

    def test_detects_query_by_keywords(self):
        queries = [
            "帮我查一下物料A001的库存",
            "查询所有未交货的订单",
            "SELECT一下客户信息",
            "看看哪些客户欠款超过100万",
            "显示最近一周的销售数据",
        ]
        for q in queries:
            result = analyze_intent(q)
            assert result.intent == Intent.QUERY, f"Failed for: {q}"

    def test_detects_build_sp_intent(self):
        results = [
            analyze_intent("我需要一套成本核算的存储过程"),
            analyze_intent("帮我写一个库存盘点的存储过程"),
            analyze_intent("构建按客户维度的利润分析存储过程体系"),
            analyze_intent("创建一个自动对账的SP"),
        ]
        for r in results:
            assert r.intent == Intent.BUILD_SP, f"Failed for: '{r.user_input}'"

    def test_detects_verify_intent(self):
        results = [
            analyze_intent("验证一下6月份的库存数据"),
            analyze_intent("帮我检查数据是否准确"),
            analyze_intent("交叉校验一下销售成本和收入"),
            analyze_intent("对比SAP报表检查数据一致性"),
        ]
        for r in results:
            assert r.intent == Intent.VERIFY, f"Failed for: '{r.user_input}'"

    def test_detects_chat_intent(self):
        results = [
            analyze_intent("SAP B1有哪些核心表"),
            analyze_intent("你好"),
            analyze_intent("怎么联系数据库"),
            analyze_intent("存储过程怎么写比较规范"),
        ]
        for r in results:
            assert r.intent == Intent.CHAT, f"Failed for: '{r.user_input}'"

    def test_stores_original_input(self):
        result = analyze_intent("查询库存数据")
        assert result.user_input == "查询库存数据"
        assert result.extracted_keywords is not None
