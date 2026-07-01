"""对话历史持久化 — 基于 aiosqlite 的轻量存储."""
from __future__ import annotations

import logging
import uuid
from typing import Optional

import aiosqlite

logger = logging.getLogger(__name__)


CREATE_CONVERSATIONS = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    database TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
)
"""

CREATE_MESSAGES = """
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    intent TEXT NOT NULL DEFAULT '',
    sql TEXT NOT NULL DEFAULT '',
    data_json TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
)
"""


class HistoryService:
    """SQLite-backed conversation history store."""

    def __init__(self, db_path: str = "data/history.db"):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def init(self) -> None:
        """Initialize database and create tables."""
        import os
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)

        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.execute(CREATE_CONVERSATIONS)
        await self._db.execute(CREATE_MESSAGES)
        await self._db.commit()
        logger.info(f"HistoryService initialized: {self.db_path}")

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    async def create_conversation(
        self, database: str = "", title: str = ""
    ) -> str:
        conv_id = str(uuid.uuid4())
        await self._db.execute(
            "INSERT INTO conversations (id, title, database) VALUES (?, ?, ?)",
            (conv_id, title, database),
        )
        await self._db.commit()
        logger.debug(f"Created conversation {conv_id}")
        return conv_id

    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        intent: str = "",
        sql: str = "",
        data_json: str = "",
    ) -> str:
        # Auto-set title from first user message (only if no explicit title set)
        if role == "user":
            row = await self._db.execute_fetchall(
                "SELECT COUNT(*) as cnt FROM messages WHERE conversation_id = ?",
                (conversation_id,),
            )
            if row and row[0]["cnt"] == 0:
                # Check if an explicit title was already provided
                conv_row = await self._db.execute_fetchall(
                    "SELECT title FROM conversations WHERE id = ?",
                    (conversation_id,),
                )
                if conv_row and not conv_row[0]["title"]:
                    title = content[:40] + ("..." if len(content) > 40 else "")
                    await self._db.execute(
                        "UPDATE conversations SET title = ? WHERE id = ?",
                        (title, conversation_id),
                    )

        msg_id = str(uuid.uuid4())
        await self._db.execute(
            """INSERT INTO messages (id, conversation_id, role, content, intent, sql, data_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (msg_id, conversation_id, role, content, intent, sql, data_json),
        )
        await self._db.commit()
        return msg_id

    async def list_conversations(
        self, database: Optional[str] = None
    ) -> list[dict]:
        if database:
            rows = await self._db.execute_fetchall(
                """SELECT c.id, c.title, c.database, c.created_at,
                          COUNT(m.id) as message_count
                   FROM conversations c
                   LEFT JOIN messages m ON c.id = m.conversation_id
                   WHERE c.database = ?
                   GROUP BY c.id
                   ORDER BY c.created_at DESC""",
                (database,),
            )
        else:
            rows = await self._db.execute_fetchall(
                """SELECT c.id, c.title, c.database, c.created_at,
                          COUNT(m.id) as message_count
                   FROM conversations c
                   LEFT JOIN messages m ON c.id = m.conversation_id
                   GROUP BY c.id
                   ORDER BY c.created_at DESC""",
            )
        return [dict(r) for r in rows]

    async def get_conversation(self, conversation_id: str) -> Optional[dict]:
        conv_rows = await self._db.execute_fetchall(
            "SELECT * FROM conversations WHERE id = ?",
            (conversation_id,),
        )
        if not conv_rows:
            return None

        conv = dict(conv_rows[0])

        msg_rows = await self._db.execute_fetchall(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
            (conversation_id,),
        )
        conv["messages"] = [dict(r) for r in msg_rows]
        return conv

    async def delete_conversation(self, conversation_id: str) -> None:
        await self._db.execute(
            "DELETE FROM messages WHERE conversation_id = ?",
            (conversation_id,),
        )
        await self._db.execute(
            "DELETE FROM conversations WHERE id = ?",
            (conversation_id,),
        )
        await self._db.commit()
        logger.debug(f"Deleted conversation {conversation_id}")
