from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from config.loader import DatabaseConfig

try:
    import pymssql
except ImportError:
    pymssql = None  # FreeTDS not available (e.g., on macOS without pymssql installed)


@dataclass
class DatabaseConnection:
    config: DatabaseConfig
    _raw_connection: Optional[object] = field(default=None, repr=False)


def create_connection(cfg: DatabaseConfig) -> DatabaseConnection:
    if cfg.type not in ("sql_server",):
        raise ValueError(
            f"Unsupported database type: {cfg.type}. "
            f"Supported: ['sql_server']"
        )
    return DatabaseConnection(config=cfg)


def _build_connect_kwargs(cfg: DatabaseConfig) -> dict:
    """构建 pymssql.connect() 参数."""
    return {
        "server": cfg.host,
        "port": str(cfg.port),
        "user": cfg.username,
        "password": cfg.password,
        "database": cfg.database,
        "login_timeout": cfg.timeout,
        "tds_version": cfg.tds_version,
        "as_dict": False,
    }


def test_connection(conn: DatabaseConnection) -> bool:
    if pymssql is None:
        raise RuntimeError("pymssql is not available on this platform")
    try:
        kwargs = _build_connect_kwargs(conn.config)
        raw = pymssql.connect(**kwargs)
        raw.close()
        return True
    except Exception:
        return False


def close_connection(conn: DatabaseConnection) -> None:
    if conn._raw_connection is not None:
        try:
            conn._raw_connection.close()
        except Exception:
            pass
        conn._raw_connection = None
