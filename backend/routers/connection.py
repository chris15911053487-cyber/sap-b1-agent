"""数据库连接测试 API."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from config.loader import load_config
from database.connector import create_connection, test_connection as test_db_conn
from backend.middleware.error_handler import AppError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["connection"])

# Injected by backend/main.py
_config_path: str = "config/config.yaml"


class ConnectionTestRequest(BaseModel):
    database: str = Field(default="", description="数据库配置名，空则取默认")


class ConnectionTestResponse(BaseModel):
    success: bool
    message: str
    database: str = ""
    host: str = ""
    port: int = 0


@router.post("/connection/test", response_model=ConnectionTestResponse)
async def test_connection(request: ConnectionTestRequest) -> ConnectionTestResponse:
    """测试指定数据库连接是否可用."""
    config = load_config(_config_path)

    db_name = request.database or config.agent.default_db
    db_config = config.databases.get(db_name)

    if not db_config:
        available = ", ".join(config.databases.keys()) if config.databases else "无"
        raise AppError(
            code="DB_NOT_FOUND",
            message=f"数据库配置 '{db_name}' 不存在。可用: {available}",
            status_code=404,
        )

    try:
        conn = create_connection(db_config)
        if test_db_conn(conn):
            return ConnectionTestResponse(
                success=True,
                message=f"连接成功: {db_config.type} @ {db_config.host}:{db_config.port}/{db_config.database}",
                database=db_name,
                host=db_config.host,
                port=db_config.port,
            )
        else:
            return ConnectionTestResponse(
                success=False,
                message=f"连接失败: {db_config.host}:{db_config.port}/{db_config.database}",
                database=db_name,
                host=db_config.host,
                port=db_config.port,
            )
    except Exception as e:
        logger.error(f"Connection test failed: {e}")
        return ConnectionTestResponse(
            success=False,
            message=f"连接异常: {e}",
            database=db_name,
            host=db_config.host,
            port=db_config.port,
        )
