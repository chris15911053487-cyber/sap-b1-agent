"""数据验证 API."""
from __future__ import annotations

import logging
from typing import Optional, Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

_PLAN_NAME = "数据验证"

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["verify"])


class VerifyRequest(BaseModel):
    database: str = Field(default="", description="目标数据库配置名")


class VerifyFindingItem(BaseModel):
    check_name: str
    status: str  # pass | fail | error
    detail: str


class VerifyResponse(BaseModel):
    plan_name: str
    total_checks: int
    passed: int
    failed: int
    pass_rate: float
    findings: list[VerifyFindingItem]


@router.post("/verify", response_model=VerifyResponse)
def run_verification(request: VerifyRequest) -> VerifyResponse:
    """执行数据验证检查（库存一致性等）。"""
    from config.loader import load_config
    from database.connector import create_connection, close_connection
    from database.executor import execute_query
    from agent.verifier import generate_standard_inventory_checks

    checks = generate_standard_inventory_checks()

    config_path = _get_config_path()
    config = load_config(config_path)

    db_name = request.database or config.agent.default_db
    db_config = config.databases.get(db_name)

    if not db_config:
        return VerifyResponse(
            plan_name=_PLAN_NAME,
            total_checks=len(checks),
            passed=0,
            failed=0,
            pass_rate=0.0,
            findings=[
                VerifyFindingItem(
                    check_name=c.name,
                    status="error",
                    detail=f"数据库 '{db_name}' 未配置",
                )
                for c in checks
            ],
        )

    findings = []
    conn = create_connection(db_config)
    try:
        for check in checks:
            try:
                result = execute_query(conn, check.check_sql)
                if not result.success:
                    findings.append(VerifyFindingItem(
                        check_name=check.name,
                        status="error",
                        detail=f"执行失败: {result.error}",
                    ))
                elif result.row_count == 0:
                    findings.append(VerifyFindingItem(
                        check_name=check.name,
                        status="pass",
                        detail="检查通过，未发现异常",
                    ))
                else:
                    findings.append(VerifyFindingItem(
                        check_name=check.name,
                        status="fail",
                        detail=f"发现 {result.row_count} 条异常数据",
                    ))
            except Exception as e:
                findings.append(VerifyFindingItem(
                    check_name=check.name,
                    status="error",
                    detail=f"执行异常: {str(e)}",
                ))
    finally:
        close_connection(conn)

    total = len(findings)
    passed = sum(1 for f in findings if f.status == "pass")
    failed = sum(1 for f in findings if f.status in ("fail", "error"))

    return VerifyResponse(
        plan_name=_PLAN_NAME,
        total_checks=total,
        passed=passed,
        failed=failed,
        pass_rate=passed / total if total > 0 else 0.0,
        findings=findings,
    )


def _get_config_path() -> str:
    import os
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "config", "config.yaml",
    )
