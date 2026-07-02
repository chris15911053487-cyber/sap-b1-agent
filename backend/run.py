"""Web 服务器入口 — uvicorn 启动 FastAPI 应用."""
from __future__ import annotations

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=False,
    )
