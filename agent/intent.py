# agent/intent.py
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class Intent(str, Enum):
    QUERY = "query"          # 自然语言查询 → SQL
    BUILD_SP = "build_sp"    # 构建存储过程体系
    VERIFY = "verify"        # 数据验证
    CHAT = "chat"            # 一般对话 / 知识问答


@dataclass
class IntentResult:
    intent: Intent
    user_input: str
    confidence: float
    extracted_keywords: list[str] = field(default_factory=list)


# 查询关键词 — 要求明确的查询动词或数据领域词
_QUERY_PATTERNS = [
    re.compile(r"(查|查询|搜索|找|看|显示|列出|获取|统计|汇总|SELECT)",
               re.IGNORECASE),
    re.compile(r"(库存|订单|客户|销售额|采购|利润|成本|数量|金额)"),
]

# 存储过程构建关键词 — 需要主动构建的动词语境
_BUILD_SP_PATTERNS = [
    re.compile(r"(存储过程体系|过程体系)", re.IGNORECASE),
    re.compile(r"(需要|写|编|创建|构建|设计|开发|生成|创建).{0,20}(存储过程|SP)"),
    re.compile(r"(设计|构建|搭).*(体系|框架|架构)"),
    re.compile(r"(CREATE\s+PROCEDURE|CREATE\s+PROC)", re.IGNORECASE),
]

# 验证关键词
_VERIFY_PATTERNS = [
    re.compile(r"(验证|校验|检查|审计|核对|对比|交叉)",
               re.IGNORECASE),
    re.compile(r"(数据|结果|报表).*(准确|正确|一致|差异|异常)"),
    re.compile(r"(和|与).*(对比|比较|核对)"),
]

# 提取可能的关键词（模块名、表名等）
_KEYWORD_PATTERN = re.compile(
    r"\b(成本|库存|销售|采购|生产|财务|利润|收入|费用|"
    r"发票|订单|工单|物料|客户|供应商|仓库|科目|"
    r"O[A-Z]{3}|[A-Z]{3}\d)\b",
    re.IGNORECASE,
)


def analyze_intent(user_input: str) -> IntentResult:
    """根据用户输入识别意图.

    使用关键词规则匹配，优先级:
    1. BUILD_SP — 明确提到存储过程
    2. VERIFY  — 明确提到验证/校验
    3. QUERY   — 明确提到查询/查找
    4. CHAT    — 默认
    """
    keywords = _KEYWORD_PATTERN.findall(user_input)

    # 检查 SP 构建意图
    for pattern in _BUILD_SP_PATTERNS:
        if pattern.search(user_input):
            return IntentResult(
                intent=Intent.BUILD_SP,
                user_input=user_input,
                confidence=0.9,
                extracted_keywords=keywords,
            )

    # 检查验证意图
    for pattern in _VERIFY_PATTERNS:
        if pattern.search(user_input):
            return IntentResult(
                intent=Intent.VERIFY,
                user_input=user_input,
                confidence=0.85,
                extracted_keywords=keywords,
            )

    # 检查查询意图
    for pattern in _QUERY_PATTERNS:
        if pattern.search(user_input):
            return IntentResult(
                intent=Intent.QUERY,
                user_input=user_input,
                confidence=0.8,
                extracted_keywords=keywords,
            )

    # 默认对话意图
    return IntentResult(
        intent=Intent.CHAT,
        user_input=user_input,
        confidence=0.5,
        extracted_keywords=keywords,
    )
