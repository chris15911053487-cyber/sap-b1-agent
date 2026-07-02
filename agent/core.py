# agent/core.py
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import AsyncGenerator, Optional

from config.loader import AppConfig, DatabaseConfig
from database.schema import SchemaCache, get_core_tables, get_related_tables
from database.connector import create_connection, close_connection
from database.executor import execute_query
from agent.intent import Intent, analyze_intent
from agent.sql_generator import build_schema_context_prompt, generate_sql
from agent.interpreter import format_result_as_markdown_table, interpret_query_result
from agent.sp_builder import build_sp_design_prompt
from agent.verifier import VerificationReport, generate_standard_inventory_checks

logger = logging.getLogger(__name__)


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
        """处理用户输入，识别意图并路由到对应处理器.

        Args:
            user_input: 用户的自然语言输入。
            no_execute: 当为 True 时，仅生成 SQL 但不执行。
            history: 可选的多轮对话历史（list of dicts, 每项含 role/content/sql/intent）。
        """
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
                             history: list[dict] | None = None) -> AsyncGenerator[str, None]:
        """异步流式处理用户输入，逐事件 yield SSE 格式字符串。

        事件类型：
        - intent: 意图识别结果
        - sql: 生成的 SQL
        - data: 查询/校验结果数据
        - explanation: 中文解读
        - done: 处理完成
        - error: 错误信息

        Args:
            user_input: 用户的自然语言输入。
            history: 可选的多轮对话历史。
        """
        import json
        from agent.intent import Intent as IntentEnum, analyze_intent as _analyze

        intent_result = _analyze(user_input)
        logger.info(
            f"Intent: {intent_result.intent.value} "
            f"(confidence: {intent_result.confidence:.2f})"
        )
        yield f"event: intent\ndata: {json.dumps({'intent': intent_result.intent.value, 'confidence': intent_result.confidence})}\n\n"

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

        yield f"event: done\ndata: {{}}\n\n"

    async def _stream_query(self, user_input: str,
                            history: list[dict] | None = None) -> AsyncGenerator[str, None]:
        import json

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
            yield f"event: error\ndata: {json.dumps({'error': gen_result.error})}\n\n"
            return

        yield f"event: sql\ndata: {json.dumps({'sql': gen_result.sql})}\n\n"

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
                    yield f"event: data\ndata: {json.dumps({'markdown': data_table})}\n\n"

                    explanation = interpret_query_result(
                        result=query_result,
                        user_question=user_input,
                        api_key=self.api_key,
                        model=self.config.agent.model,
                        base_url=self.base_url,
                        history=history,
                    )
                    yield f"event: explanation\ndata: {json.dumps({'text': explanation})}\n\n"
                else:
                    error_msg = f"SQL 执行出错: {query_result.error}"
                    yield f"event: error\ndata: {json.dumps({'error': error_msg})}\n\n"
            finally:
                close_connection(conn)
        else:
            yield f"event: data\ndata: {json.dumps({'markdown': ''})}\n\n"
            text = f"SQL 已生成（未连接数据库）:\n```sql\n{gen_result.sql}\n```\n\n{gen_result.explanation}"
            yield f"event: explanation\ndata: {json.dumps({'text': text})}\n\n"

    async def _stream_build_sp(self, user_input: str) -> AsyncGenerator[str, None]:
        import json

        schema_context = self._get_schema_context()
        design_prompt = build_sp_design_prompt(
            requirement=user_input,
            schema_context=schema_context,
        )

        text = (
            f"## 存储过程体系设计 Prompt\n\n"
            f"已根据您的需求构建完整的设计 Prompt，请将以下内容提供给 AI 进行存储过程架构设计:\n\n"
            f"```\n{design_prompt}\n```\n\n"
            f"### 后续步骤\n"
            f"1. 将上述 Prompt 提交给 AI 模型生成 SP 架构设计\n"
            f"2. 审核生成的 JSON 架构设计\n"
            f"3. 逐个生成 T-SQL 代码\n"
            f"4. 在数据库上部署验证"
        )
        yield f"event: explanation\ndata: {json.dumps({'text': text})}\n\n"

    async def _stream_verify(self, user_input: str) -> AsyncGenerator[str, None]:
        import json

        checks = generate_standard_inventory_checks()

        db_name = self.config.agent.default_db
        db_config = self.config.databases.get(db_name)
        if not db_config:
            text = f"## 标准验证方案\n\n已验证检查项: {len(checks)} 项\n\n未连接数据库，请在连接后重试。"
            yield f"event: explanation\ndata: {json.dumps({'text': text})}\n\n"
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
        yield f"event: data\ndata: {json.dumps({'findings': findings_json, 'pass_rate': report.pass_rate, 'total': report.total_checks, 'passed': report.passed, 'failed': report.failed})}\n\n"
        yield f"event: explanation\ndata: {json.dumps({'text': report.summary_text()})}\n\n"

    async def _stream_chat(self, user_input: str) -> AsyncGenerator[str, None]:
        import json

        result = self._handle_chat(user_input)
        yield f"event: explanation\ndata: {json.dumps({'text': result.explanation})}\n\n"

    def _get_schema_context(self, keywords: Optional[list[str]] = None) -> str:
        """构建当前对话的 Schema 上下文.

        如果提供了关键词，会尝试包含相关的表。
        """
        tables = {}
        # 始终包含核心业务表
        always_include = ["OITM", "OCRD", "ORDR", "OINV", "OPOR", "OWOR"]
        for name in always_include:
            schema = self.schema_cache.get(name)
            if schema:
                tables[name] = schema

        # 尝试根据关键词匹配更多表
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
        """处理自然语言查询.

        Args:
            user_input: 用户的自然语言查询。
            no_execute: 为 True 时仅生成 SQL，不执行。
            history: 可选的多轮对话历史。
        """
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

        # --no-execute 模式：跳过数据库执行，仅返回生成的 SQL
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

        # 获取数据库连接并执行
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

        # 调用 build_sp_design_prompt 构建 AI 设计 prompt
        design_prompt = build_sp_design_prompt(
            requirement=user_input,
            schema_context=schema_context,
        )

        return AgentResponse(
            intent="build_sp",
            sql="",
            explanation=(
                f"## 存储过程体系设计 Prompt\n\n"
                f"已根据您的需求构建完整的设计 Prompt，请将以下内容提供给 AI 进行存储过程架构设计:\n\n"
                f"```\n{design_prompt}\n```\n\n"
                f"### 后续步骤\n"
                f"1. 将上述 Prompt 提交给 AI 模型生成 SP 架构设计\n"
                f"2. 审核生成的 JSON 架构设计\n"
                f"3. 逐个生成 T-SQL 代码\n"
                f"4. 在数据库上部署验证"
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
