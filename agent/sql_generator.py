# agent/sql_generator.py
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

from openai import OpenAI

from database.schema import TableSchema

logger = logging.getLogger(__name__)


@dataclass
class SqlGenerationResult:
    sql: str
    explanation: str
    success: bool = True
    error: str = ""


def _extract_json_balanced(text: str) -> dict | None:
    """通过扫描平衡大括号提取最外层的 JSON 对象."""
    for start_idx, ch in enumerate(text):
        if ch == '{':
            depth = 1
            for end_idx in range(start_idx + 1, len(text)):
                c = text[end_idx]
                if c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0:
                        candidate = text[start_idx:end_idx + 1]
                        try:
                            return json.loads(candidate)
                        except json.JSONDecodeError:
                            break
    return None


def build_schema_context_prompt(tables: dict[str, TableSchema]) -> str:
    """构建包含表结构的 Schema 上下文，注入到 AI prompt 中."""
    lines = ["# SAP B1 数据库表结构\n"]
    for table_name, schema in tables.items():
        lines.append(f"## {table_name} — {schema.description}")
        lines.append("| 字段 | 类型 | 说明 |")
        lines.append("|------|------|------|")
        for col in schema.columns:
            pk_mark = " 🔑PK" if col.is_primary_key else ""
            null_mark = " NULL" if col.is_nullable else " NOT NULL"
            desc = col.description or ""
            lines.append(f"| {col.name} | {col.data_type}{null_mark} | {desc}{pk_mark} |")

        if schema.relations:
            lines.append("\n关联关系:")
            for rel in schema.relations:
                lines.append(f"  - {rel.target_table}: {rel.join_condition} ({rel.description})")
        lines.append("")
    return "\n".join(lines)


def build_sql_generation_prompt(
    user_input: str,
    schema_context: str,
) -> str:
    """构建 Text-to-SQL 的完整 prompt."""
    return f"""你是一个 SAP Business One 数据库专家，精通 SQL Server T-SQL。

# 数据库 Schema
{schema_context}

# SAP B1 表命名规则
- O + 3字母 = 主表头（如 ORDR = 销售订单头）
- 3字母 + 1 = 行明细（如 RDR1 = 销售订单行）
- @ 前缀 = 用户自定义表 (UDT)
- U_ 前缀 = 用户自定义字段 (UDF)
- CANCELED = 'N' 表示未取消的单据

# 要求
1. 仅生成 SELECT 查询，不要修改数据
2. 使用 TOP 限制返回行数（默认 TOP 100）
3. 对日期字段使用正确的日期函数（SQL Server: DATEADD, DATEDIFF, GETDATE）
4. JOIN 条件使用 SAP B1 标准关联关系
5. 对可能为 NULL 的字段使用 ISNULL 处理
6. 添加必要的 WHERE 过滤条件（如 CANCELED = 'N'）

# 用户需求
{user_input}

请严格按以下 JSON 格式返回（不要包含其他字符）:
{{"sql": "<生成的SQL语句>", "explanation": "<对SQL逻辑的中文解释>"}}
"""


def generate_sql(
    user_input: str,
    schema_context: str,
    api_key: str,
    model: str = "deepseek-chat",
    base_url: str = "https://api.deepseek.com",
    history: list[dict] | None = None,
) -> SqlGenerationResult:
    """调用 DeepSeek API 将自然语言转换为 SQL.

    Args:
        user_input: 用户的自然语言查询
        schema_context: 预构建的 Schema 上下文字符串
        api_key: DeepSeek API Key
        model: 使用的模型 ID
        base_url: API Base URL
        history: 可选的多轮对话历史，用于上下文感知。
    """
    prompt = build_sql_generation_prompt(user_input, schema_context)

    messages: list[dict] = []

    # Add conversation history for multi-turn context (last 10 exchanges max)
    if history:
        for h in history[-10:]:
            role = h.get("role", "user")
            content = h.get("content", "")
            if role == "user":
                messages.append({"role": "user", "content": content})
            elif role == "assistant":
                prev_sql = h.get("sql", "")
                parts = [content]
                if prev_sql:
                    parts.append(f"\n[执行的SQL: {prev_sql}]")
                messages.append({"role": "assistant", "content": "\n".join(parts)})

    # Add current prompt
    messages.append({"role": "user", "content": prompt})

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            max_tokens=2000,
            temperature=0.0,
            messages=messages,
        )

        response_text = response.choices[0].message.content

        # 尝试直接解析
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            # 从 markdown 代码块中提取 JSON
            json_block_match = re.search(
                r'```(?:json)?\s*\n?(\{.*?\n?\})\s*\n?```',
                response_text,
                re.DOTALL,
            )
            if json_block_match:
                try:
                    data = json.loads(json_block_match.group(1))
                except json.JSONDecodeError:
                    data = None
            else:
                data = None

            # 扫描平衡大括号
            if data is None:
                data = _extract_json_balanced(response_text)

            if data is None:
                raise ValueError(f"Cannot parse AI response as JSON: {response_text[:500]}")

        sql = data.get("sql", "").strip()
        explanation = data.get("explanation", "").strip()

        if not sql:
            return SqlGenerationResult(
                sql="",
                explanation="",
                success=False,
                error="AI returned empty SQL",
            )

        logger.info(f"Generated SQL: {sql[:200]}...")
        return SqlGenerationResult(
            sql=sql,
            explanation=explanation,
            success=True,
        )

    except Exception as e:
        logger.error(f"SQL generation failed: {e}")
        return SqlGenerationResult(
            sql="",
            explanation="",
            success=False,
            error=str(e),
        )
