# agent/interpreter.py
from __future__ import annotations

import logging
import os

from openai import OpenAI

from database.executor import QueryResult

logger = logging.getLogger(__name__)


def format_result_as_markdown_table(result: QueryResult) -> str:
    """将查询结果格式化为 Markdown 表格."""
    if not result.success:
        return f"❌ 查询失败: {result.error}"

    if not result.columns or result.row_count == 0:
        return "_没有数据，请检查查询条件或确认数据库中有相关数据。_"

    lines = []
    lines.append("| " + " | ".join(result.columns) + " |")
    lines.append("|" + "|".join(["------"] * len(result.columns)) + "|")
    for row in result.rows:
        cells = [str(v) if v is not None else "NULL" for v in row]
        lines.append("| " + " | ".join(cells) + " |")

    lines.append(f"\n_共 {result.row_count} 条记录_")
    return "\n".join(lines)


def build_interpretation_prompt(user_question: str, data_table: str) -> str:
    """构建结果解读的 AI prompt."""
    return f"""你是一个 SAP Business One 数据分析师，擅长从数据中解读业务洞察。

# 用户问题
{user_question}

# 查询结果
{data_table}

# 要求
请用中文对以上结果进行简洁的解读，包括:
1. 数据核心发现（2-3句话概括）
2. 如果有多个数据行，指出最重要的几条（Top 3）
3. 如果有异常值或值得注意的数据点，请指出
4. 如果数值较大，可以换算为"万元"等单位使阅读更友好

控制在 150 字以内，直接给出解读，不要问问题。
"""


def interpret_query_result(
    result: QueryResult,
    user_question: str,
    api_key: str,
    model: str = "deepseek-chat",
    base_url: str = "https://api.deepseek.com",
) -> str:
    """调用 DeepSeek API 对查询结果进行自然语言解读."""
    if not result.success:
        return f"查询执行失败: {result.error}"

    if result.row_count == 0:
        return "查询未返回任何数据，请调整查询条件后重试。"

    data_table = format_result_as_markdown_table(result)
    prompt = build_interpretation_prompt(user_question, data_table)

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            max_tokens=500,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )
        interpretation = response.choices[0].message.content.strip()
        logger.info(f"Interpretation generated ({len(interpretation)} chars)")
        return interpretation

    except Exception as e:
        logger.warning(f"Interpretation failed, returning raw data: {e}")
        return f"数据结果如下:\n\n{data_table}"
