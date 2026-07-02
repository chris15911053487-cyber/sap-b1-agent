"""统一错误处理 — 所有 API 异常返回统一 JSON 格式."""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    """应用层异常，携带错误码供前端展示."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 500,
        details: Optional[dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


def register_exception_handlers(app: FastAPI) -> None:
    """向 FastAPI 应用注册全局异常处理器."""

    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        logger.error(f"[{request_id}] AppError: {exc.code} - {exc.message}")
        body: dict[str, Any] = {
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": request_id,
            }
        }
        if exc.details:
            body["error"]["details"] = exc.details
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        logger.exception(f"[{request_id}] Unhandled exception: {exc}")
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "服务器内部错误，请查看日志或联系管理员。",
                    "request_id": request_id,
                }
            },
        )
