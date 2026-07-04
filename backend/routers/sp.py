"""手动部署存储过程 API — 用户确认编辑后的 SQL 代码再执行部署."""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from config.loader import load_config
from agent.sp_deployer import deploy_sp_batch, verify_sp_batch

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
