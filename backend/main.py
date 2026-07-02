"""FastAPI 应用入口."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.middleware.error_handler import register_exception_handlers
from backend.services.history_service import HistoryService
from backend.services.chat_service import ChatService
from backend.routers import chat, history, connection, schema, verification

load_dotenv()

logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "config", "config.yaml"
)
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期 — 启停时初始化/清理资源."""
    # Startup
    logger.info("Starting SAP B1 DB Agent API...")

    # Initialize history service
    db_path = os.path.join(DATA_DIR, "history.db")
    history_svc = HistoryService(db_path=db_path)
    await history_svc.init()

    # Initialize chat service
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        logger.warning("DEEPSEEK_API_KEY not set — chat will fail until configured")
        api_key = ""

    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

    chat_svc = ChatService(
        config_path=CONFIG_PATH,
        api_key=api_key,
        base_url=base_url,
        history_service=history_svc,
    )

    # Inject services into routers
    chat._chat_service = chat_svc
    history._history_service = history_svc
    connection._config_path = CONFIG_PATH

    logger.info("Services initialized. API ready.")

    yield

    # Shutdown
    logger.info("Shutting down...")
    await history_svc.close()


app = FastAPI(
    title="SAP B1 DB Agent API",
    description="SAP Business One 数据库 AI 智能体 Web API",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS — allow dev frontend origin; in production Nginx handles this
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:80", "http://127.0.0.1:80"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Error handling
register_exception_handlers(app)

# Routers
app.include_router(chat.router)
app.include_router(history.router)
app.include_router(connection.router)
app.include_router(schema.router)
app.include_router(verification.router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
