from __future__ import annotations

import re
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from database.connector import DatabaseConnection, _build_connect_kwargs

try:
    import pymssql
except ImportError:
    pymssql = None  # FreeTDS not available

logger = logging.getLogger(__name__)

# 危险 SQL 模式（生产库禁止执行）
_DANGEROUS_PATTERNS = [
    re.compile(r"\bDROP\s+(TABLE|DATABASE|INDEX|VIEW|PROCEDURE|FUNCTION)\b", re.IGNORECASE),
    re.compile(r"\bTRUNCATE\s+TABLE\b", re.IGNORECASE),
    re.compile(r"\bDELETE\s+FROM\b(?!.*\bWHERE\b)", re.IGNORECASE),
    re.compile(r"\bALTER\s+(TABLE|DATABASE)\b", re.IGNORECASE),
]


@dataclass
class QueryResult:
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    row_count: int = 0
    success: bool = True
    error: str = ""
    execution_time_ms: float = 0.0


@dataclass
class ExecResult:
    success: bool = True
    error: str = ""
    rows_affected: int = 0
    execution_time_ms: float = 0.0


def is_dangerous_sql(sql: str) -> bool:
    for pattern in _DANGEROUS_PATTERNS:
        if pattern.search(sql):
            return True
    return False


def _get_raw_connection(conn: DatabaseConnection):
    if pymssql is None:
        raise RuntimeError("pymssql is not available on this platform")
    if conn._raw_connection is None:
        kwargs = _build_connect_kwargs(conn.config)
        conn._raw_connection = pymssql.connect(**kwargs)
    return conn._raw_connection


def _add_top_clause(sql: str, max_rows: int) -> str:
    stripped = sql.strip()
    if stripped.upper().startswith("SELECT") and "TOP" not in stripped.upper():
        return stripped.replace("SELECT", f"SELECT TOP {max_rows}", 1)
    return sql


def execute_query(
    conn: DatabaseConnection,
    sql: str,
    params: Optional[tuple] = None,
    max_rows: int = 1000,
) -> QueryResult:
    start = time.time()
    try:
        sql = _add_top_clause(sql, max_rows)
        logger.info(f"Executing query: {sql[:200]}...")

        raw = _get_raw_connection(conn)
        cursor = raw.cursor()
        cursor.execute(sql, params or ())

        columns = [col[0] for col in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
        execution_ms = (time.time() - start) * 1000

        logger.info(f"Query returned {len(rows)} rows in {execution_ms:.0f}ms")

        return QueryResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            success=True,
            execution_time_ms=execution_ms,
        )
    except Exception as e:
        execution_ms = (time.time() - start) * 1000
        logger.error(f"Query failed after {execution_ms:.0f}ms: {e}")
        return QueryResult(
            success=False,
            error=str(e),
            execution_time_ms=execution_ms,
        )


def execute_statement(
    conn: DatabaseConnection,
    sql: str,
    readonly: bool = False,
) -> ExecResult:
    start = time.time()

    if is_dangerous_sql(sql):
        msg = (
            "Blocked dangerous SQL operation. DROP/TRUNCATE/DELETE-without-WHERE "
            "are not allowed through this interface."
        )
        logger.warning(msg)
        return ExecResult(success=False, error=msg)

    try:
        logger.info(f"Executing statement: {sql[:200]}...")

        raw = _get_raw_connection(conn)
        cursor = raw.cursor()
        cursor.execute(sql)
        raw.commit()

        rows_affected = cursor.rowcount
        execution_ms = (time.time() - start) * 1000

        logger.info(f"Statement completed: {rows_affected} rows affected in {execution_ms:.0f}ms")

        return ExecResult(
            success=True,
            rows_affected=rows_affected,
            execution_time_ms=execution_ms,
        )
    except Exception as e:
        execution_ms = (time.time() - start) * 1000
        logger.error(f"Statement failed after {execution_ms:.0f}ms: {e}")
        return ExecResult(
            success=False,
            error=str(e),
            execution_time_ms=execution_ms,
        )
