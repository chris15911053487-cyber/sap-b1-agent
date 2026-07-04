# agent/sp_deployer.py
"""存储过程部署与验证模块 — 自动执行 CREATE PROCEDURE 并验证运行结果."""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

from database.connector import DatabaseConnection, create_connection, close_connection
from config.loader import DatabaseConfig

try:
    import pymssql
except ImportError:
    pymssql = None

logger = logging.getLogger("agent.sp_deployer")


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class DeployResult:
    """单个 SP 部署结果."""
    name: str
    success: bool = True
    error: str = ""
    action: str = ""  # "created" | "replaced" | "skipped"
    execution_time_ms: float = 0.0


@dataclass
class DeployReport:
    """整体部署报告."""
    results: list[DeployResult] = field(default_factory=list)
    log_table_created: bool = False

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def succeeded(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.success)


@dataclass
class VerifyResult:
    """单个 SP 验证结果."""
    name: str
    success: bool = True
    error: str = ""
    row_count: int = 0
    execution_time_ms: float = 0.0
    sample_output: str = ""  # 前几行结果预览


@dataclass
class VerifyReport:
    """整体验证报告."""
    results: list[VerifyResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.success)


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

def _get_raw_conn(conn: DatabaseConnection):
    """Get or create a raw pymssql connection."""
    from database.executor import _get_raw_connection
    return _get_raw_connection(conn)


def _ensure_log_table(conn: DatabaseConnection) -> bool:
    """Create ZZ_SP_LOG table if it doesn't exist. Returns True if created."""
    raw = _get_raw_conn(conn)
    cursor = raw.cursor()

    # Check if table exists
    cursor.execute("""
        SELECT 1 FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_NAME = 'ZZ_SP_LOG'
    """)
    if cursor.fetchone():
        return False

    # Create the log table
    create_sql = """
    CREATE TABLE ZZ_SP_LOG (
        LogID INT IDENTITY(1,1) PRIMARY KEY,
        SPName NVARCHAR(200) NOT NULL,
        Status NVARCHAR(50) NOT NULL,
        ErrorMsg NVARCHAR(MAX) NULL,
        ErrorMessage NVARCHAR(MAX) NULL,
        ExecTime DATETIME DEFAULT GETDATE(),
        ExecutionTime INT NULL,
        CreatedDate DATETIME DEFAULT GETDATE()
    )
    """
    cursor.execute(create_sql)
    raw.commit()
    logger.info("Created ZZ_SP_LOG table")
    return True


def _sp_exists(conn: DatabaseConnection, sp_name: str) -> bool:
    """Check if a stored procedure already exists."""
    raw = _get_raw_conn(conn)
    cursor = raw.cursor()
    cursor.execute(
        "SELECT 1 FROM sys.procedures WHERE name = %s",
        (sp_name,)
    )
    return cursor.fetchone() is not None


def _drop_sp(conn: DatabaseConnection, sp_name: str) -> None:
    """Drop an existing stored procedure."""
    raw = _get_raw_conn(conn)
    cursor = raw.cursor()
    cursor.execute(f"DROP PROCEDURE IF EXISTS [dbo].[{sp_name}]")
    raw.commit()
    logger.info(f"Dropped existing SP: {sp_name}")


def _extract_sp_name_from_code(code: str) -> Optional[str]:
    """Extract the procedure name from CREATE PROCEDURE statement."""
    match = re.search(
        r'CREATE\s+PROCEDURE\s+\[?(?:dbo\]?\.)?\[?(\w+)\]?',
        code,
        re.IGNORECASE,
    )
    return match.group(1) if match else None


def _execute_ddl(conn: DatabaseConnection, sql: str) -> tuple[bool, str]:
    """Execute a DDL statement (CREATE/ALTER PROCEDURE). Returns (success, error)."""
    raw = _get_raw_conn(conn)
    cursor = raw.cursor()
    try:
        cursor.execute(sql)
        raw.commit()
        return True, ""
    except Exception as e:
        try:
            raw.rollback()
        except Exception:
            pass
        return False, str(e)


# ---------------------------------------------------------------------------
# Public API: Deploy
# ---------------------------------------------------------------------------

def deploy_sp(
    db_config: DatabaseConfig,
    sp_name: str,
    generated_code: str,
) -> DeployResult:
    """Deploy a single stored procedure to the database.

    Steps:
    1. If SP exists → DROP it first
    2. Execute CREATE PROCEDURE
    3. Return result
    """
    start = time.time()
    conn = create_connection(db_config)

    try:
        # Determine if SP already exists
        exists = _sp_exists(conn, sp_name)

        # Remove ALL GO batch separators (pymssql doesn't support them)
        # GO must appear on its own line (possibly with whitespace) to avoid matching
        # identifiers like "CARGO", "CATEGORY_GO", column aliases, etc.
        deploy_sql = re.sub(
            r'^\s*GO\s*$', '', generated_code.strip(),
            flags=re.IGNORECASE | re.MULTILINE,
        ).strip()

        # Drop if exists
        if exists:
            _drop_sp(conn, sp_name)

        # Execute CREATE PROCEDURE
        success, error = _execute_ddl(conn, deploy_sql)
        elapsed = (time.time() - start) * 1000

        if success:
            action = "replaced" if exists else "created"
            logger.info(f"Deployed SP '{sp_name}' ({action}) in {elapsed:.0f}ms")
            return DeployResult(
                name=sp_name,
                success=True,
                action=action,
                execution_time_ms=elapsed,
            )
        else:
            logger.error(f"Failed to deploy SP '{sp_name}': {error}")
            return DeployResult(
                name=sp_name,
                success=False,
                error=error,
                action="failed",
                execution_time_ms=elapsed,
            )
    except Exception as e:
        elapsed = (time.time() - start) * 1000
        logger.error(f"Deploy error for '{sp_name}': {e}")
        return DeployResult(
            name=sp_name,
            success=False,
            error=str(e),
            action="failed",
            execution_time_ms=elapsed,
        )
    finally:
        close_connection(conn)


def deploy_sp_batch(
    db_config: DatabaseConfig,
    procedures: list[dict],
    execution_order: list[str],
) -> DeployReport:
    """Deploy multiple SPs in dependency order.

    Args:
        db_config: Database configuration
        procedures: List of procedure dicts with 'name' and 'generated_code'
        execution_order: Ordered list of SP names (topological order)
    """
    report = DeployReport()

    # Ensure ZZ_SP_LOG table exists
    conn = create_connection(db_config)
    try:
        report.log_table_created = _ensure_log_table(conn)
    except Exception as e:
        logger.warning(f"Could not ensure ZZ_SP_LOG table: {e}")
    finally:
        close_connection(conn)

    # Build name → procedure mapping
    proc_map = {p["name"]: p for p in procedures}

    # Deploy in order
    for sp_name in execution_order:
        proc = proc_map.get(sp_name)
        if not proc:
            report.results.append(DeployResult(
                name=sp_name,
                success=False,
                error=f"Procedure '{sp_name}' not found in generated code",
                action="skipped",
            ))
            continue

        result = deploy_sp(db_config, sp_name, proc["generated_code"])
        report.results.append(result)

        # If a deployment fails, skip dependent procedures
        if not result.success:
            # Find procedures that depend on this one
            remaining = execution_order[execution_order.index(sp_name) + 1:]
            for dep_name in remaining:
                dep_proc = proc_map.get(dep_name)
                if dep_proc:
                    deps = dep_proc.get("dependencies", [])
                    if sp_name in deps:
                        report.results.append(DeployResult(
                            name=dep_name,
                            success=False,
                            error=f"跳过: 依赖的 '{sp_name}' 部署失败",
                            action="skipped",
                        ))
            break

    return report


# ---------------------------------------------------------------------------
# Public API: Verify
# ---------------------------------------------------------------------------

def verify_sp(
    db_config: DatabaseConfig,
    sp_name: str,
    parameters: dict[str, str],
) -> VerifyResult:
    """Verify a deployed SP by executing it with @Debug=1.

    If the SP has parameters, runs with defaults (NULL or provided values).
    """
    start = time.time()
    conn = create_connection(db_config)

    try:
        raw = _get_raw_conn(conn)
        cursor = raw.cursor()

        # Build EXEC statement with @Debug=1 if parameter exists
        param_parts = []
        if "@Debug" in parameters or any("Debug" in k for k in parameters):
            param_parts.append("@Debug = 1")

        # For other parameters, pass NULL to use defaults
        for param_name in parameters:
            if "Debug" in param_name:
                continue
            param_parts.append(f"{param_name} = NULL")

        param_str = ", ".join(param_parts) if param_parts else ""
        exec_sql = f"EXEC [dbo].[{sp_name}] {param_str}".strip()

        logger.info(f"Verifying SP: {exec_sql}")

        cursor.execute(exec_sql)

        # Try to fetch results
        row_count = 0
        sample_output = ""
        if cursor.description:
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchall()
            row_count = len(rows)

            # Build sample output (first 3 rows)
            sample_lines = [" | ".join(str(c) for c in columns)]
            sample_lines.append("-" * len(sample_lines[0]))
            for row in rows[:3]:
                sample_lines.append(" | ".join(str(v) for v in row))
            if row_count > 3:
                sample_lines.append(f"... (共 {row_count} 行)")
            sample_output = "\n".join(sample_lines)

        elapsed = (time.time() - start) * 1000
        logger.info(f"SP '{sp_name}' verification passed: {row_count} rows in {elapsed:.0f}ms")

        return VerifyResult(
            name=sp_name,
            success=True,
            row_count=row_count,
            execution_time_ms=elapsed,
            sample_output=sample_output,
        )

    except Exception as e:
        elapsed = (time.time() - start) * 1000
        error_msg = str(e)
        logger.error(f"SP '{sp_name}' verification failed: {error_msg}")
        return VerifyResult(
            name=sp_name,
            success=False,
            error=error_msg,
            execution_time_ms=elapsed,
        )
    finally:
        close_connection(conn)


def verify_sp_batch(
    db_config: DatabaseConfig,
    procedures: list[dict],
    execution_order: list[str],
) -> VerifyReport:
    """Verify all deployed SPs in execution order.

    Args:
        db_config: Database configuration
        procedures: List of procedure dicts with 'name' and 'parameters'
        execution_order: Ordered list of SP names
    """
    report = VerifyReport()

    proc_map = {p["name"]: p for p in procedures}

    for sp_name in execution_order:
        proc = proc_map.get(sp_name, {})
        params = proc.get("parameters", {})

        result = verify_sp(db_config, sp_name, params)
        report.results.append(result)

    return report
