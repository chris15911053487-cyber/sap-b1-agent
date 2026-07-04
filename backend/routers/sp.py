"""手动部署存储过程 API — 用户确认编辑后的 SQL 代码再执行部署."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from config.loader import load_config
from agent.sp_deployer import deploy_sp_batch, verify_sp_batch, deploy_sp
from agent.sp_validator import run_validation, run_validation_batch, ValidationReport
from agent.sp_builder import SPSpec, generate_sp_code, regenerate_sp_with_feedback
from database.schema import SchemaCache, get_core_tables, get_related_tables
from agent.sql_generator import build_schema_context_prompt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sp", tags=["sp"])

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config", "config.yaml"
)


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class SpProcedureInput(BaseModel):
    """单个存储过程的部署输入."""
    name: str
    generated_code: str = Field(..., description="用户确认/编辑后的完整 SQL 代码")
    dependencies: list[str] = Field(default_factory=list)
    parameters: dict[str, str] = Field(default_factory=dict)


class SpDeployRequest(BaseModel):
    """手动部署请求."""
    procedures: list[SpProcedureInput]
    execution_order: list[str]
    database: str = Field(default="", description="目标数据库配置名，空则使用默认")


class SpDeployResultItem(BaseModel):
    name: str
    success: bool
    action: str
    error: str = ""
    execution_time_ms: float = 0.0


class SpVerifyResultItem(BaseModel):
    name: str
    success: bool
    error: str = ""
    row_count: int = 0
    execution_time_ms: float = 0.0
    sample_output: str = ""


class SpDeployResponse(BaseModel):
    """部署 + 验证响应."""
    deploy_total: int = 0
    deploy_succeeded: int = 0
    deploy_failed: int = 0
    log_table_created: bool = False
    deploy_results: list[SpDeployResultItem] = Field(default_factory=list)
    verify_total: int = 0
    verify_passed: int = 0
    verify_failed: int = 0
    verify_results: list[SpVerifyResultItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/deploy", response_model=SpDeployResponse)
async def deploy_stored_procedures(request: SpDeployRequest) -> SpDeployResponse:
    """手动部署存储过程 — 用户在前端编辑确认后调用此接口执行部署.

    流程:
    1. 按 execution_order 顺序执行 CREATE PROCEDURE
    2. 部署成功的 SP 自动验证 (EXEC @Debug=1)
    3. 返回部署 + 验证结果
    """
    config = load_config(CONFIG_PATH)

    # Determine target database
    db_name = request.database or config.agent.default_db
    db_config = config.databases.get(db_name)

    if not db_config:
        return SpDeployResponse(
            deploy_total=len(request.procedures),
            deploy_failed=len(request.procedures),
            deploy_results=[
                SpDeployResultItem(
                    name=p.name,
                    success=False,
                    action="failed",
                    error=f"数据库配置 '{db_name}' 不存在",
                )
                for p in request.procedures
            ],
        )

    # Prepare procedures data for deploy_sp_batch
    procedures_data = [
        {
            "name": p.name,
            "generated_code": p.generated_code,
            "dependencies": p.dependencies,
            "parameters": p.parameters,
        }
        for p in request.procedures
    ]

    # Deploy
    import asyncio

    deploy_report = await asyncio.to_thread(
        deploy_sp_batch,
        db_config=db_config,
        procedures=procedures_data,
        execution_order=request.execution_order,
    )

    deploy_results = [
        SpDeployResultItem(
            name=r.name,
            success=r.success,
            action=r.action,
            error=r.error,
            execution_time_ms=r.execution_time_ms,
        )
        for r in deploy_report.results
    ]

    # Verify successfully deployed SPs
    verify_results: list[SpVerifyResultItem] = []
    verify_total = 0
    verify_passed = 0
    verify_failed = 0

    if deploy_report.succeeded > 0:
        deployed_names = [r.name for r in deploy_report.results if r.success]
        deployed_procs = [p for p in procedures_data if p["name"] in deployed_names]
        deployed_order = [n for n in request.execution_order if n in deployed_names]

        verify_report = await asyncio.to_thread(
            verify_sp_batch,
            db_config=db_config,
            procedures=deployed_procs,
            execution_order=deployed_order,
        )

        verify_total = verify_report.total
        verify_passed = verify_report.passed
        verify_failed = verify_report.failed
        verify_results = [
            SpVerifyResultItem(
                name=r.name,
                success=r.success,
                error=r.error,
                row_count=r.row_count,
                execution_time_ms=r.execution_time_ms,
                sample_output=r.sample_output,
            )
            for r in verify_report.results
        ]

    return SpDeployResponse(
        deploy_total=deploy_report.total,
        deploy_succeeded=deploy_report.succeeded,
        deploy_failed=deploy_report.failed,
        log_table_created=deploy_report.log_table_created,
        deploy_results=deploy_results,
        verify_total=verify_total,
        verify_passed=verify_passed,
        verify_failed=verify_failed,
        verify_results=verify_results,
    )


# ---------------------------------------------------------------------------
# 业务对账验证 + AI 自修复
# ---------------------------------------------------------------------------

def _build_schema_context(keywords: Optional[list[str]] = None) -> str:
    """构建 Schema 上下文，供修复 prompt 使用."""
    cache = SchemaCache()
    core_tables = get_core_tables()
    for table in core_tables.values():
        cache.add(table)

    tables = {}
    always_include = ["OITM", "OCRD", "ORDR", "OINV", "OPOR", "OWOR", "OITW", "OACT"]
    for name in always_include:
        schema = cache.get(name)
        if schema:
            tables[name] = schema

    if keywords:
        for kw in keywords:
            upper = kw.upper()
            if cache.has(upper):
                tables[upper] = cache.get(upper)
            for rel_name in get_related_tables(upper):
                rel = cache.get(rel_name)
                if rel:
                    tables[rel_name] = rel

    return build_schema_context_prompt(tables)


def _report_to_dict(report: ValidationReport) -> dict:
    """把 ValidationReport 转成可 JSON 化的 dict."""
    return {
        "sp_name": report.sp_name,
        "total": report.total,
        "passed": report.passed,
        "failed": report.failed,
        "has_error_failures": report.has_error_failures,
        "results": [
            {
                "name": r.name,
                "description": r.description,
                "category": r.category,
                "severity": r.severity,
                "passed": r.passed,
                "assertion": r.assertion,
                "actual_values": r.actual_values,
                "detail": r.detail,
                "check_sql": r.check_sql,
            }
            for r in report.results
        ],
    }


class SpValidateProcInput(BaseModel):
    name: str
    verification_checks: list[dict] = Field(default_factory=list)


class SpValidateRequest(BaseModel):
    procedures: list[SpValidateProcInput]
    database: str = Field(default="", description="目标数据库配置名，空则使用默认")


class SpValidateResponse(BaseModel):
    reports: list[dict] = Field(default_factory=list)
    total_checks: int = 0
    total_passed: int = 0
    total_failed: int = 0
    has_error_failures: bool = False


@router.post("/validate", response_model=SpValidateResponse)
async def validate_stored_procedures(request: SpValidateRequest) -> SpValidateResponse:
    """运行业务对账断言，验证已部署 SP 产出的数据是否正确.

    半自动流程的第一步：只做验证并展示 pass/fail，不自动修复。
    """
    config = load_config(CONFIG_PATH)
    db_name = request.database or config.agent.default_db
    db_config = config.databases.get(db_name)

    if not db_config:
        return SpValidateResponse()

    procedures_data = [
        {"name": p.name, "verification_checks": p.verification_checks}
        for p in request.procedures
    ]

    reports = await asyncio.to_thread(
        run_validation_batch,
        db_config=db_config,
        procedures=procedures_data,
    )

    report_dicts = [_report_to_dict(r) for r in reports]
    total_checks = sum(r.total for r in reports)
    total_passed = sum(r.passed for r in reports)
    total_failed = sum(r.failed for r in reports)
    has_error = any(r.has_error_failures for r in reports)

    return SpValidateResponse(
        reports=report_dicts,
        total_checks=total_checks,
        total_passed=total_passed,
        total_failed=total_failed,
        has_error_failures=has_error,
    )


class SpRepairProcInput(BaseModel):
    name: str
    description: str = ""
    output_table: str = ""
    business_logic: str = ""
    parameters: dict[str, str] = Field(default_factory=dict)
    generated_code: str
    verification_checks: list[dict] = Field(default_factory=list)


class SpRepairRequest(BaseModel):
    procedure: SpRepairProcInput
    database: str = Field(default="")
    max_iterations: int = Field(default=3, ge=1, le=5)


class SpRepairIteration(BaseModel):
    iteration: int
    generated_code: str = ""
    deploy_success: bool = False
    deploy_error: str = ""
    validation_report: dict = Field(default_factory=dict)
    passed: bool = False
    llm_error: str = ""


class SpRepairResponse(BaseModel):
    sp_name: str
    success: bool = False
    message: str = ""
    iterations: list[SpRepairIteration] = Field(default_factory=list)
    final_code: str = ""
    final_report: dict = Field(default_factory=dict)


def _run_repair_loop(
    db_config,
    proc: SpRepairProcInput,
    api_key: str,
    base_url: str,
    model: str,
    max_iterations: int,
) -> SpRepairResponse:
    """同步执行修复循环：重新生成 → 部署 → 再验证，最多 max_iterations 次."""
    spec = SPSpec(
        name=proc.name,
        description=proc.description,
        output_table=proc.output_table,
        parameters=proc.parameters,
        business_logic=proc.business_logic,
        verification_checks=proc.verification_checks,
    )
    schema_context = _build_schema_context([proc.output_table] if proc.output_table else None)

    response = SpRepairResponse(sp_name=proc.name)
    current_code = proc.generated_code
    checks = proc.verification_checks

    # 取当前失败的断言作为反馈起点
    current_report = run_validation(db_config, proc.name, checks)
    failed_checks = [
        {
            "name": r.name,
            "description": r.description,
            "check_sql": r.check_sql,
            "assertion": r.assertion,
            "actual_values": r.actual_values,
            "detail": r.detail,
        }
        for r in current_report.results if not r.passed
    ]

    if not failed_checks:
        response.success = True
        response.message = "当前无失败断言，无需修复"
        response.final_code = current_code
        response.final_report = _report_to_dict(current_report)
        return response

    for i in range(1, max_iterations + 1):
        iteration = SpRepairIteration(iteration=i)

        # 1. 让 LLM 基于失败断言重新生成实现体
        try:
            new_body = regenerate_sp_with_feedback(
                spec=spec,
                current_code=current_code,
                failed_checks=failed_checks,
                schema_context=schema_context,
                api_key=api_key,
                model=model,
                base_url=base_url,
            )
            new_code = generate_sp_code(spec, implementation_body=new_body)
            iteration.generated_code = new_code
        except Exception as e:
            iteration.llm_error = str(e)
            response.iterations.append(iteration)
            response.message = f"第 {i} 次修复：LLM 生成失败: {e}"
            break

        # 2. 重新部署
        deploy_result = deploy_sp(db_config, proc.name, new_code)
        iteration.deploy_success = deploy_result.success
        iteration.deploy_error = deploy_result.error

        if not deploy_result.success:
            response.iterations.append(iteration)
            current_code = new_code  # 仍记录，供下一轮参考
            response.message = f"第 {i} 次修复：部署失败: {deploy_result.error}"
            # 部署失败也继续尝试下一轮（把部署错误纳入反馈）
            failed_checks = failed_checks + [{
                "name": "部署错误",
                "description": "生成的 SP 无法成功部署",
                "check_sql": "",
                "assertion": "",
                "actual_values": {},
                "detail": deploy_result.error,
            }]
            continue

        # 3. 重新验证
        new_report = run_validation(db_config, proc.name, checks)
        iteration.validation_report = _report_to_dict(new_report)
        iteration.passed = not new_report.has_error_failures
        response.iterations.append(iteration)

        current_code = new_code

        if not new_report.has_error_failures:
            response.success = True
            response.message = f"第 {i} 次修复后业务对账全部通过 ✅"
            response.final_code = new_code
            response.final_report = _report_to_dict(new_report)
            return response

        # 更新失败断言，进入下一轮
        failed_checks = [
            {
                "name": r.name,
                "description": r.description,
                "check_sql": r.check_sql,
                "assertion": r.assertion,
                "actual_values": r.actual_values,
                "detail": r.detail,
            }
            for r in new_report.results if not r.passed
        ]

    # 循环结束仍未通过
    response.final_code = current_code
    if response.iterations and response.iterations[-1].validation_report:
        response.final_report = response.iterations[-1].validation_report
    if not response.message:
        response.message = f"已尝试 {max_iterations} 次修复仍未全部通过，建议人工介入"
    return response


@router.post("/repair", response_model=SpRepairResponse)
async def repair_stored_procedure(request: SpRepairRequest) -> SpRepairResponse:
    """AI 自修复：针对业务对账失败的 SP，反馈失败详情让 LLM 修正并重新验证.

    半自动流程的第二步：由用户在看到验证结果后主动触发。
    """
    config = load_config(CONFIG_PATH)
    db_name = request.database or config.agent.default_db
    db_config = config.databases.get(db_name)

    if not db_config:
        return SpRepairResponse(
            sp_name=request.procedure.name,
            success=False,
            message=f"数据库配置 '{db_name}' 不存在",
        )

    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    if not api_key:
        return SpRepairResponse(
            sp_name=request.procedure.name,
            success=False,
            message="未配置 DEEPSEEK_API_KEY，无法调用 AI 修复",
        )

    result = await asyncio.to_thread(
        _run_repair_loop,
        db_config=db_config,
        proc=request.procedure,
        api_key=api_key,
        base_url=base_url,
        model=config.agent.model,
        max_iterations=request.max_iterations,
    )
    return result
