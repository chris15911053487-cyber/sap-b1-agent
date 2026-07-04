# agent/core.py
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Optional

from config.loader import AppConfig, DatabaseConfig
from database.schema import SchemaCache, get_core_tables, get_related_tables
from database.connector import create_connection, close_connection
from database.executor import execute_query
from agent.intent import Intent, analyze_intent
from agent.sql_generator import build_schema_context_prompt, generate_sql
from agent.interpreter import format_result_as_markdown_table, interpret_query_result
from agent.sp_builder import (
    build_sp_design_prompt,
    generate_sp_architecture,
    generate_sp_code,
    generate_sp_implementation,
)
from agent.verifier import VerificationReport, generate_standard_inventory_checks

logger = logging.getLogger(__name__)


def _sse(event: str, data: Any) -> dict:
    """构建 sse-starlette 兼容的 SSE 事件 dict."""
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


@dataclass
class AgentResponse:
    intent: str
    success: bool = True
    sql: str = ""
    data_table: str = ""
    explanation: str = ""
    error: str = ""


class DBAgent:
    def __init__(self, config: AppConfig, api_key: str, base_url: str = "https://api.deepseek.com"):
        self.config = config
        self.api_key = api_key
        self.base_url = base_url
        self.schema_cache = SchemaCache()

        # 预加载核心表结构
        core_tables = get_core_tables()
        for table in core_tables.values():
            self.schema_cache.add(table)

        # 数据库连接（延迟连接）
        self._connections: dict[str, object] = {}

    def process(self, user_input: str, no_execute: bool = False,
                history: list[dict] | None = None) -> AgentResponse:
        """处理用户输入，识别意图并路由到对应处理器."""
        intent_result = analyze_intent(user_input)
        logger.info(
            f"Intent: {intent_result.intent.value} "
            f"(confidence: {intent_result.confidence:.2f})"
        )

        if intent_result.intent == Intent.QUERY:
            return self._handle_query(user_input, no_execute=no_execute, history=history)
        elif intent_result.intent == Intent.BUILD_SP:
            return self._handle_build_sp(user_input)
        elif intent_result.intent == Intent.VERIFY:
            return self._handle_verify(user_input)
        else:
            return self._handle_chat(user_input)

    async def process_stream(self, user_input: str,
                             history: list[dict] | None = None) -> AsyncGenerator[dict, None]:
        """异步流式处理用户输入，逐事件 yield SSE dict.

        每个 yield 的 dict 包含 event 和 data 两个 key，
        由 sse-starlette 格式化为标准 SSE 事件。
        """
        from agent.intent import Intent as IntentEnum, analyze_intent as _analyze

        intent_result = _analyze(user_input)
        logger.info(
            f"Intent: {intent_result.intent.value} "
            f"(confidence: {intent_result.confidence:.2f})"
        )
        yield _sse("intent", {"intent": intent_result.intent.value, "confidence": intent_result.confidence})

        if intent_result.intent == IntentEnum.QUERY:
            async for event in self._stream_query(user_input, history=history):
                yield event
        elif intent_result.intent == IntentEnum.BUILD_SP:
            async for event in self._stream_build_sp(user_input):
                yield event
        elif intent_result.intent == IntentEnum.VERIFY:
            async for event in self._stream_verify(user_input):
                yield event
        else:
            async for event in self._stream_chat(user_input):
                yield event

        yield _sse("done", {})

    async def _stream_query(self, user_input: str,
                            history: list[dict] | None = None) -> AsyncGenerator[dict, None]:
        schema_context = self._get_schema_context()

        gen_result = generate_sql(
            user_input=user_input,
            schema_context=schema_context,
            api_key=self.api_key,
            model=self.config.agent.model,
            base_url=self.base_url,
            history=history,
        )

        if not gen_result.success:
            yield _sse("error", {"error": gen_result.error})
            return

        yield _sse("sql", {"sql": gen_result.sql})

        db_name = self.config.agent.default_db
        db_config = self.config.databases.get(db_name)
        if db_config:
            conn = create_connection(db_config)
            try:
                query_result = execute_query(
                    conn,
                    gen_result.sql,
                    max_rows=self.config.agent.max_query_rows,
                )

                if query_result.success:
                    data_table = format_result_as_markdown_table(query_result)
                    yield _sse("data", {"markdown": data_table})

                    explanation = interpret_query_result(
                        result=query_result,
                        user_question=user_input,
                        api_key=self.api_key,
                        model=self.config.agent.model,
                        base_url=self.base_url,
                        history=history,
                    )
                    yield _sse("explanation", {"text": explanation})
                else:
                    error_msg = f"SQL 执行出错: {query_result.error}"
                    yield _sse("error", {"error": error_msg})
            finally:
                close_connection(conn)
        else:
            yield _sse("data", {"markdown": ""})
            text = f"SQL 已生成（未连接数据库）:\n```sql\n{gen_result.sql}\n```\n\n{gen_result.explanation}"
            yield _sse("explanation", {"text": text})

    async def _stream_build_sp(self, user_input: str) -> AsyncGenerator[dict, None]:
        import asyncio

        schema_context = self._get_schema_context()

        # 1. 调用 LLM 生成 SP 架构设计（在线程池中执行，避免阻塞事件循环）
        yield _sse("progress", {"stage": "arch", "message": "正在设计存储过程体系架构..."})

        arch_result = await asyncio.to_thread(
            generate_sp_architecture,
            user_input=user_input,
            schema_context=schema_context,
            api_key=self.api_key,
            model=self.config.agent.model,
            base_url=self.base_url,
        )

        if not arch_result.success:
            yield _sse("error", {"error": f"SP 架构生成失败: {arch_result.error}"})
            return

        arch = arch_result.architecture

        yield _sse("progress", {"stage": "arch_done", "message": f"架构设计完成: {arch.name}，共 {len(arch.procedures)} 个存储过程，开始生成实现代码..."})

        # 2. 为每个 SP 调用 LLM 生成真实 T-SQL 实现代码
        procedures_data = []
        for i, spec in enumerate(arch.procedures):
            yield _sse("progress", {"stage": "impl", "message": f"正在生成 {spec.name} 实现代码 ({i+1}/{len(arch.procedures)})..."})

            # 在线程池中执行 LLM 调用，避免阻塞事件循环
            impl_body = await asyncio.to_thread(
                generate_sp_implementation,
                spec=spec,
                schema_context=schema_context,
                api_key=self.api_key,
                model=self.config.agent.model,
                base_url=self.base_url,
            )
            code = generate_sp_code(spec, implementation_body=impl_body)
            procedures_data.append({
                "name": spec.name,
                "description": spec.description,
                "dependencies": spec.dependencies,
                "output_table": spec.output_table,
                "parameters": spec.parameters,
                "business_logic": spec.business_logic,
                "verification_checks": spec.verification_checks,
                "generated_code": code,
            })

        arch_data = {
            "name": arch.name,
            "description": arch.description,
            "design_notes": arch.design_notes,
            "procedures": procedures_data,
            "execution_order": arch.execution_order,
        }

        yield _sse("sp_arch", arch_data)

        # 3. 生成文本总结 — 不再自动部署，等待用户确认
        exec_order_lines = "\n".join(
            f"{i+1}. {name}" for i, name in enumerate(arch.execution_order)
        )

        text = (
            f"## 存储过程体系: {arch.name}\n\n"
            f"{arch.description}\n\n"
            f"### 设计说明\n\n{arch.design_notes}\n\n"
            f"### 包含 {len(arch.procedures)} 个存储过程，执行顺序:\n\n"
            f"{exec_order_lines}\n\n"
            f"---\n\n"
            f"> 请检查下方生成的 T-SQL 代码，可直接编辑修改，确认无误后点击「部署」按钮执行。"
        )
        yield _sse("explanation", {"text": text})

    async def _stream_verify(self, user_input: str) -> AsyncGenerator[dict, None]:
        checks = generate_standard_inventory_checks()

        db_name = self.config.agent.default_db
        db_config = self.config.databases.get(db_name)
        if not db_config:
            text = f"## 标准验证方案\n\n已验证检查项: {len(checks)} 项\n\n未连接数据库，请在连接后重试。"
            yield _sse("explanation", {"text": text})
            return

        from agent.verifier import VerificationFinding

        conn = create_connection(db_config)
        try:
            findings = []
            for check in checks:
                result = execute_query(conn, check.check_sql)
                if not result.success:
                    findings.append(VerificationFinding(
                        check_name=check.name,
                        status="error",
                        detail=f"执行失败: {result.error}",
                    ))
                elif result.row_count == 0:
                    findings.append(VerificationFinding(
                        check_name=check.name,
                        status="pass",
                        detail="检查通过，未发现异常",
                    ))
                else:
                    findings.append(VerificationFinding(
                        check_name=check.name,
                        status="fail",
                        detail=f"发现 {result.row_count} 条异常数据",
                    ))
        finally:
            close_connection(conn)

        report = VerificationReport(plan_name="数据验证", findings=findings)

        findings_json = [
            {
                "check_name": f.check_name,
                "status": f.status,
                "detail": f.detail,
            }
            for f in report.findings
        ]
        yield _sse("data", {"findings": findings_json, "pass_rate": report.pass_rate, "total": report.total_checks, "passed": report.passed, "failed": report.failed})
        yield _sse("explanation", {"text": report.summary_text()})

    async def _stream_chat(self, user_input: str) -> AsyncGenerator[dict, None]:
        result = self._handle_chat(user_input)
        yield _sse("explanation", {"text": result.explanation})

    def _get_schema_context(self, keywords: Optional[list[str]] = None) -> str:
        """构建当前对话的 Schema 上下文."""
        tables = {}
        always_include = ["OITM", "OCRD", "ORDR", "OINV", "OPOR", "OWOR"]
        for name in always_include:
            schema = self.schema_cache.get(name)
            if schema:
                tables[name] = schema

        if keywords:
            for kw in keywords:
                upper = kw.upper()
                if upper.startswith("O") or upper.startswith("@"):
                    if self.schema_cache.has(upper):
                        tables[upper] = self.schema_cache.get(upper)
                    related = get_related_tables(upper)
                    for rel_name in related:
                        rel = self.schema_cache.get(rel_name)
                        if rel:
                            tables[rel_name] = rel

        return build_schema_context_prompt(tables)

    def _handle_query(self, user_input: str, no_execute: bool = False,
                      history: list[dict] | None = None) -> AgentResponse:
        """处理自然语言查询."""
        schema_context = self._get_schema_context()

        gen_result = generate_sql(
            user_input=user_input,
            schema_context=schema_context,
            api_key=self.api_key,
            model=self.config.agent.model,
            base_url=self.base_url,
            history=history,
        )

        if not gen_result.success:
            return AgentResponse(
                intent="query",
                success=False,
                error=gen_result.error,
            )

        if no_execute:
            return AgentResponse(
                intent="query",
                sql=gen_result.sql,
                data_table="",
                explanation=(
                    f"SQL 已生成（未执行）:\n```sql\n{gen_result.sql}\n```\n\n"
                    f"{gen_result.explanation}"
                ),
                success=True,
            )

        db_name = self.config.agent.default_db
        db_config = self.config.databases.get(db_name)
        if db_config:
            conn = create_connection(db_config)
            try:
                query_result = execute_query(
                    conn,
                    gen_result.sql,
                    max_rows=self.config.agent.max_query_rows,
                )

                if query_result.success:
                    data_table = format_result_as_markdown_table(query_result)
                    explanation = interpret_query_result(
                        result=query_result,
                        user_question=user_input,
                        api_key=self.api_key,
                        model=self.config.agent.model,
                        base_url=self.base_url,
                        history=history,
                    )
                else:
                    data_table = f"查询失败: {query_result.error}"
                    explanation = f"SQL 执行出错: {query_result.error}"
            finally:
                close_connection(conn)
        else:
            data_table = ""
            explanation = (
                f"SQL 已生成（未连接数据库）:\n```sql\n{gen_result.sql}\n```\n\n"
                f"{gen_result.explanation}"
            )

        return AgentResponse(
            intent="query",
            sql=gen_result.sql,
            data_table=data_table,
            explanation=explanation,
            success=True,
        )

    def _handle_build_sp(self, user_input: str) -> AgentResponse:
        """处理存储过程构建请求."""
        schema_context = self._get_schema_context()

        arch_result = generate_sp_architecture(
            user_input=user_input,
            schema_context=schema_context,
            api_key=self.api_key,
            model=self.config.agent.model,
            base_url=self.base_url,
        )

        if not arch_result.success:
            return AgentResponse(
                intent="build_sp",
                success=False,
                error=f"SP 架构生成失败: {arch_result.error}",
            )

        arch = arch_result.architecture
        exec_order_lines = "\n".join(
            f"{i+1}. {name}" for i, name in enumerate(arch.execution_order)
        )

        return AgentResponse(
            intent="build_sp",
            sql="",
            explanation=(
                f"## 存储过程体系: {arch.name}\n\n"
                f"{arch.description}\n\n"
                f"### 设计说明\n\n{arch.design_notes}\n\n"
                f"### 包含 {len(arch.procedures)} 个存储过程，执行顺序:\n\n"
                f"{exec_order_lines}\n\n"
                f"> 可通过流式接口查看每个 SP 的 T-SQL 骨架代码。"
            ),
            success=True,
        )

    def _handle_verify(self, user_input: str) -> AgentResponse:
        """处理数据验证请求."""
        checks = generate_standard_inventory_checks()

        db_name = self.config.agent.default_db
        db_config = self.config.databases.get(db_name)
        if not db_config:
            return AgentResponse(
                intent="verify",
                explanation=f"## 标准验证方案\n\n已验证检查项: {len(checks)} 项\n\n未连接数据库，请在连接后重试。",
                success=True,
            )

        from agent.verifier import VerificationFinding

        conn = create_connection(db_config)
        try:
            findings = []
            for check in checks:
                result = execute_query(conn, check.check_sql)
                if not result.success:
                    findings.append(VerificationFinding(
                        check_name=check.name,
                        status="error",
                        detail=f"执行失败: {result.error}",
                    ))
                elif result.row_count == 0:
                    findings.append(VerificationFinding(
                        check_name=check.name,
                        status="pass",
                        detail="检查通过，未发现异常",
                    ))
                else:
                    findings.append(VerificationFinding(
                        check_name=check.name,
                        status="fail",
                        detail=f"发现 {result.row_count} 条异常数据",
                    ))
        finally:
            close_connection(conn)

        report = VerificationReport(plan_name="数据验证", findings=findings)
        return AgentResponse(
            intent="verify",
            explanation=report.summary_text(),
            success=True,
        )

    def _handle_chat(self, user_input: str) -> AgentResponse:
        """处理一般对话."""
        greetings = ["你好", "hi", "hello", "您好", "在吗", "在不在"]
        if any(g in user_input.lower() for g in greetings):
            return AgentResponse(
                intent="chat",
                explanation=(
                    "你好！我是 SAP B1 数据库智能助手。我可以帮你:\n"
                    "- **查询数据** — 用中文描述需求，我生成 SQL 并执行\n"
                    "- **构建存储过程** — 设计完整的 SP 体系\n"
                    "- **验证数据** — 自动检查数据准确性\n\n"
                    "请告诉我你需要什么？"
                ),
                success=True,
            )

        return AgentResponse(
            intent="chat",
            explanation=(
                "我可以帮你:\n"
                "1. 查询数据（例如: '查一下上个月销售前10的客户'）\n"
                "2. 构建存储过程（例如: '我需要成本核算的SP体系'）\n"
                "3. 验证数据（例如: '检查6月的库存是否准确'）\n\n"
                "请描述你的具体需求。"
            ),
            success=True,
        )
