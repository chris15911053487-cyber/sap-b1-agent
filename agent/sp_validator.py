# agent/sp_validator.py
"""业务对账验证模块 — 执行验证断言并判定数据正确性.

工作流:
1. 每个 SP 附带一组"业务对账断言"(verification_checks)
2. 部署 + 运行 SP 后，执行每条断言的 check_sql（返回单行结果）
3. 用安全求值器对照 assertion 表达式判定 pass/fail
4. 返回验证报告，供前端展示、供 AI 自修复参考
"""
from __future__ import annotations

import ast
import logging
import operator
from dataclasses import dataclass, field
from typing import Any

from database.connector import DatabaseConnection, create_connection, close_connection
from database.executor import execute_query
from config.loader import DatabaseConfig

logger = logging.getLogger("agent.sp_validator")


# ---------------------------------------------------------------------------
# 安全断言表达式求值器
# ---------------------------------------------------------------------------

# 仅允许的二元运算符
_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.FloorDiv: operator.floordiv,
}

# 仅允许的比较运算符
_ALLOWED_COMPARE = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}

# 仅允许的一元运算符
_ALLOWED_UNARY = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
    ast.Not: operator.not_,
}

# 仅允许的布尔运算符
_ALLOWED_BOOLOPS = {ast.And: all, ast.Or: any}

# 仅允许调用的白名单函数
_ALLOWED_FUNCS = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "len": len,
    "float": float,
    "int": int,
    "bool": bool,
    "sum": sum,
}


class AssertionEvalError(Exception):
    """断言表达式求值错误."""


def _eval_node(node: ast.AST, variables: dict[str, Any]) -> Any:
    """递归求值 AST 节点，只允许白名单操作."""
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, variables)

    # 常量
    if isinstance(node, ast.Constant):
        return node.value

    # 变量名 — 只能引用 check_sql 返回的列
    if isinstance(node, ast.Name):
        if node.id in variables:
            return variables[node.id]
        raise AssertionEvalError(f"未知变量 '{node.id}'（不在 check_sql 返回列中）")

    # 二元运算
    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_BINOPS:
            raise AssertionEvalError(f"不允许的运算符: {op_type.__name__}")
        left = _eval_node(node.left, variables)
        right = _eval_node(node.right, variables)
        return _ALLOWED_BINOPS[op_type](left, right)

    # 一元运算
    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_UNARY:
            raise AssertionEvalError(f"不允许的一元运算符: {op_type.__name__}")
        return _ALLOWED_UNARY[op_type](_eval_node(node.operand, variables))

    # 比较 (支持链式比较 a < b < c)
    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, variables)
        for op, comparator in zip(node.ops, node.comparators):
            op_type = type(op)
            if op_type not in _ALLOWED_COMPARE:
                raise AssertionEvalError(f"不允许的比较运算符: {op_type.__name__}")
            right = _eval_node(comparator, variables)
            if not _ALLOWED_COMPARE[op_type](left, right):
                return False
            left = right
        return True

    # 布尔运算 and/or
    if isinstance(node, ast.BoolOp):
        op_type = type(node.op)
        values = [_eval_node(v, variables) for v in node.values]
        if op_type is ast.And:
            return all(values)
        if op_type is ast.Or:
            return any(values)
        raise AssertionEvalError("不允许的布尔运算符")

    # 白名单函数调用
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise AssertionEvalError("只允许调用白名单函数")
        fname = node.func.id
        if fname not in _ALLOWED_FUNCS:
            raise AssertionEvalError(f"不允许的函数: {fname}")
        args = [_eval_node(a, variables) for a in node.args]
        return _ALLOWED_FUNCS[fname](*args)

    raise AssertionEvalError(f"不允许的表达式节点: {type(node).__name__}")


def safe_eval_assertion(expr: str, variables: dict[str, Any]) -> bool:
    """安全求值断言表达式，返回布尔结果.

    Args:
        expr: Python 布尔表达式，如 "abs(a - b) < 1" 或 "cnt == 0"
        variables: check_sql 返回的列名 → 值 的映射

    Raises:
        AssertionEvalError: 表达式非法或引用未知变量
    """
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise AssertionEvalError(f"断言表达式语法错误: {e}")

    result = _eval_node(tree, variables)
    return bool(result)


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    """单条断言的验证结果."""
    name: str
    description: str
    category: str
    severity: str          # "error" | "warning"
    passed: bool
    assertion: str
    actual_values: dict = field(default_factory=dict)  # check_sql 返回的列值
    detail: str = ""       # 说明或错误信息
    check_sql: str = ""


@dataclass
class ValidationReport:
    """一个 SP 的业务对账验证报告."""
    sp_name: str
    results: list[CheckResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    @property
    def has_error_failures(self) -> bool:
        """是否存在 severity=error 的失败项（需要修复）."""
        return any(not r.passed and r.severity == "error" for r in self.results)


# ---------------------------------------------------------------------------
# 断言执行器
# ---------------------------------------------------------------------------

def _run_single_check(conn: DatabaseConnection, check: dict) -> CheckResult:
    """执行单条断言检查."""
    name = check.get("name", "未命名检查")
    check_sql = check.get("check_sql", "").strip()
    assertion = check.get("assertion", "").strip()
    severity = (check.get("severity") or "error").lower()

    base = CheckResult(
        name=name,
        description=check.get("description", ""),
        category=check.get("category", "对账"),
        severity=severity,
        passed=False,
        assertion=assertion,
        check_sql=check_sql,
    )

    if not check_sql or not assertion:
        base.detail = "断言缺少 check_sql 或 assertion"
        return base

    # 执行 check_sql
    query_result = execute_query(conn, check_sql, max_rows=10)
    if not query_result.success:
        base.detail = f"check_sql 执行失败: {query_result.error}"
        return base

    if query_result.row_count == 0 or not query_result.rows:
        base.detail = "check_sql 未返回任何行，无法判定"
        return base

    # 取第一行作为变量映射
    first_row = query_result.rows[0]
    variables = dict(zip(query_result.columns, first_row))
    # 额外暴露 row_count
    variables.setdefault("row_count", query_result.row_count)

    # 序列化实际值（Decimal / datetime 转 str 以便 JSON 化）
    base.actual_values = {
        k: (float(v) if isinstance(v, (int, float)) else str(v))
        for k, v in variables.items()
    }

    # 求值断言
    try:
        passed = safe_eval_assertion(assertion, variables)
        base.passed = passed
        if passed:
            base.detail = "对账通过"
        else:
            vals = ", ".join(f"{k}={v}" for k, v in base.actual_values.items())
            base.detail = f"对账不通过 — 实际值: {vals}"
    except AssertionEvalError as e:
        base.detail = f"断言求值错误: {e}"
        base.passed = False

    return base


def run_validation(
    db_config: DatabaseConfig,
    sp_name: str,
    checks: list[dict],
) -> ValidationReport:
    """对单个 SP 运行其全部业务对账断言.

    Args:
        db_config: 数据库配置
        sp_name: 存储过程名（用于报告标识）
        checks: verification_checks 列表

    Returns:
        ValidationReport
    """
    report = ValidationReport(sp_name=sp_name)

    if not checks:
        logger.info(f"SP '{sp_name}' 无业务对账断言，跳过验证")
        return report

    conn = create_connection(db_config)
    try:
        for check in checks:
            result = _run_single_check(conn, check)
            report.results.append(result)
            status = "PASS" if result.passed else "FAIL"
            logger.info(f"[{sp_name}] 断言 '{result.name}': {status} — {result.detail}")
    finally:
        close_connection(conn)

    return report


def run_validation_batch(
    db_config: DatabaseConfig,
    procedures: list[dict],
) -> list[ValidationReport]:
    """对多个 SP 批量运行业务对账断言.

    Args:
        db_config: 数据库配置
        procedures: 每项含 'name' 和 'verification_checks'

    Returns:
        每个含断言的 SP 对应一份 ValidationReport
    """
    reports: list[ValidationReport] = []
    for proc in procedures:
        checks = proc.get("verification_checks") or []
        if not checks:
            continue
        report = run_validation(db_config, proc["name"], checks)
        reports.append(report)
    return reports
