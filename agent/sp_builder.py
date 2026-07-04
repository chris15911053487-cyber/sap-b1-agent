# agent/sp_builder.py
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from openai import OpenAI

logger = logging.getLogger(__name__)


@dataclass
class VerificationCheck:
    name: str
    description: str
    category: str
    check_sql: str
    expected_result: str = ""


@dataclass
class VerificationPlan:
    name: str
    description: str
    checks: list[VerificationCheck] = field(default_factory=list)


@dataclass
class VerificationFinding:
    check_name: str
    status: str          # "pass" | "fail" | "error"
    detail: str
    affected_items: list[str] = field(default_factory=list)


@dataclass
class VerificationReport:
    plan_name: str
    findings: list[VerificationFinding] = field(default_factory=list)

    @property
    def total_checks(self) -> int:
        return len(self.findings)

    @property
    def passed(self) -> int:
        return sum(1 for f in self.findings if f.status == "pass")

    @property
    def failed(self) -> int:
        return sum(1 for f in self.findings if f.status == "fail")

    @property
    def pass_rate(self) -> float:
        if self.total_checks == 0:
            return 0.0
        return self.passed / self.total_checks

    def summary_text(self) -> str:
        lines = [
            f"## 验证报告: {self.plan_name}",
            f"",
            f"| 状态 | 检查项 | 详情 |",
            f"|------|--------|------|",
        ]
        for f in self.findings:
            status_icon = {"pass": "✅", "fail": "❌", "error": "⚠️"}.get(f.status, "❓")
            lines.append(f"| {status_icon} | {f.check_name} | {f.detail} |")

        lines.append("")
        lines.append(f"**通过率: {self.passed}/{self.total_checks} ({self.pass_rate:.0%})**")
        return "\n".join(lines)


def generate_standard_inventory_checks() -> list[VerificationCheck]:
    """生成标准库存验证检查项."""
    return [
        VerificationCheck(
            name="库存余额一致性",
            description="仓库汇总库存(OITW) vs 物料主数据库存(OITM.OnHand)",
            category="库存",
            check_sql="""
                SELECT T0.ItemCode, T0.OnHand AS OITM_OnHand,
                       SUM(T1.OnHand) AS OITW_SumOnHand,
                       T0.OnHand - SUM(T1.OnHand) AS Diff
                FROM OITM T0
                INNER JOIN OITW T1 ON T0.ItemCode = T1.ItemCode
                GROUP BY T0.ItemCode, T0.OnHand
                HAVING T0.OnHand <> SUM(T1.OnHand)
            """,
            expected_result="无差异（返回0行）",
        ),
        VerificationCheck(
            name="负库存检查",
            description="检查是否存在库存为负的物料",
            category="库存",
            check_sql="""
                SELECT ItemCode, WhsCode, OnHand
                FROM OITW
                WHERE OnHand < 0
            """,
            expected_result="无数据（所有物料库存 >= 0）",
        ),
        VerificationCheck(
            name="库存金额vs总账",
            description="物料库存金额汇总 vs 总账库存科目余额",
            category="库存",
            check_sql="""
                SELECT
                    (SELECT SUM(T0.OnHand * T1.AvgPrice)
                     FROM OITW T0
                     INNER JOIN OITM T1 ON T0.ItemCode = T1.ItemCode) AS InventoryValue,
                    (SELECT SUM(CurrTotal)
                     FROM OACT
                     WHERE AcctCode LIKE '1%') AS GLInventoryValue
            """,
            expected_result="两者金额接近（差异 < 1%）",
        ),
        VerificationCheck(
            name="期初期末连续性",
            description="本月期初 = 上月期末（期间连续性验证）",
            category="库存",
            check_sql="""
                -- 此检查需要指定期间参数 @CurrentPeriod, @PreviousPeriod
                SELECT '需指定期间参数运行此检查' AS Note
            """,
            expected_result="月初=上月期末",
        ),
    ]


# ---------------------------------------------------------------------------
# 存储过程体系设计
# ---------------------------------------------------------------------------

@dataclass
class SPSpec:
    name: str
    description: str
    dependencies: list[str] = field(default_factory=list)
    output_table: str = ""
    parameters: dict[str, str] = field(default_factory=dict)
    business_logic: str = ""
    # 业务对账断言 — 每项含 name/description/category/check_sql/assertion/severity
    verification_checks: list[dict] = field(default_factory=list)


@dataclass
class SPArchitecture:
    name: str
    description: str
    procedures: list[SPSpec] = field(default_factory=list)
    design_notes: str = ""

    @property
    def execution_order(self) -> list[str]:
        """根据依赖关系返回执行顺序（拓扑排序），检测循环依赖."""
        ordered = []
        remaining = list(self.procedures)
        resolved = set()

        while remaining:
            progress = False
            for sp in list(remaining):
                if all(d in resolved for d in sp.dependencies):
                    ordered.append(sp.name)
                    resolved.add(sp.name)
                    remaining.remove(sp)
                    progress = True
                elif not sp.dependencies:
                    ordered.append(sp.name)
                    resolved.add(sp.name)
                    remaining.remove(sp)
                    progress = True
            if not progress:
                # 本轮未解决任何依赖 — 存在循环依赖
                unresolved = {sp.name: sp.dependencies for sp in remaining}
                raise ValueError(
                    f"Circular dependency detected among procedures: {unresolved}"
                )
        return ordered


@dataclass
class SPArchitectureResult:
    """generate_sp_architecture 的返回类型."""
    architecture: Optional[SPArchitecture] = None
    success: bool = True
    error: str = ""

def _normalize_checks(raw) -> list[dict]:
    """规范化 LLM 返回的 verification_checks，过滤无效项."""
    if not isinstance(raw, list):
        return []
    checks: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        check_sql = (item.get("check_sql") or "").strip()
        assertion = (item.get("assertion") or "").strip()
        # 必须同时有 check_sql 和 assertion 才是有效断言
        if not check_sql or not assertion:
            continue
        checks.append({
            "name": (item.get("name") or "未命名检查").strip(),
            "description": (item.get("description") or "").strip(),
            "category": (item.get("category") or "对账").strip(),
            "check_sql": check_sql,
            "assertion": assertion,
            "severity": (item.get("severity") or "error").strip().lower(),
        })
    return checks



def _extract_json_balanced(text: str) -> dict | None:
    """通过扫描平衡大括号提取最外层的 JSON 对象."""
    for start_idx, ch in enumerate(text):
        if ch == '{':
            depth = 1
            for end_idx in range(start_idx + 1, len(text)):
                c = text[end_idx]
                if c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0:
                        candidate = text[start_idx:end_idx + 1]
                        try:
                            return json.loads(candidate)
                        except json.JSONDecodeError:
                            break
    return None


def build_sp_design_prompt(requirement: str, schema_context: str) -> str:
    return f"""你是一位资深的 SAP Business One 数据库架构师，擅长设计存储过程体系。

# 数据库 Schema
{schema_context}

# 命名规范
- SP_模板: SP_{{Module}}_{{Function}}
- Module: Cost, INV, Sales, Purchase, Production, Finance, Report
- 中间表前缀: ZZ_
- 日志表: ZZ_SP_LOG (列: SPName, Status, ErrorMsg, ExecTime)

# 每个 SP 的要求
- 职责单一：一个 SP 只做一件事
- 头部注释块完整（功能、依赖、输出）
- BEGIN TRY...CATCH 错误处理
- 事务控制
- @Debug BIT = 0 调试参数
- 执行日志记录到 ZZ_SP_LOG

# 用户需求
{requirement}

请设计存储过程体系，按以下 JSON 格式返回:
{{
  "name": "体系名称",
  "description": "体系说明",
  "design_notes": "设计思路和注意事项",
  "procedures": [
    {{
      "name": "SP_XXX_YYY",
      "description": "功能描述",
      "dependencies": ["SP_前置名称"],
      "output_table": "ZZ_输出表名",
      "parameters": {{"@Period": "VARCHAR(7)"}},
      "business_logic": "详细的业务逻辑描述，供后续代码生成使用",
      "verification_checks": [
        {{
          "name": "对账检查名称",
          "description": "这条检查验证什么业务规则",
          "category": "对账",
          "check_sql": "SELECT ... 返回单行、列名清晰的聚合结果",
          "assertion": "引用 check_sql 返回列名的布尔表达式",
          "severity": "error"
        }}
      ]
    }}
  ]
}}

# 业务对账断言规范（verification_checks）— 非常重要
每个 SP 必须附带 1-4 条**业务对账断言**，用于在 SP 运行后自动验证数据正确性。要求:
- **check_sql**: 必须是 SELECT 查询，返回**单行**结果，列名要清晰（用 AS 别名）。可跨表勾稽。
- **assertion**: 一个 Python 布尔表达式，只能引用 check_sql 返回的列名。支持的函数: abs, round, min, max。
  例如返回列 `inv_value` 和 `gl_value` 时: `abs(inv_value - gl_value) / gl_value < 0.01`
  例如返回列 `neg_cnt` 时: `neg_cnt == 0`
- **category**: "对账"(跨表勾稽) | "完整性"(非空/无NULL) | "合理性"(无负值/范围)
- **severity**: "error"(必须通过) | "warning"(建议通过)

# 业务对账断言示例（SAP B1 场景）
- 库存金额勾稽总账: check_sql 同时算出物料库存总值和总账1开头科目余额, assertion 判断差异<1%
- 输出表非空: SELECT COUNT(*) AS cnt FROM ZZ_输出表, assertion: cnt > 0
- 无负成本: SELECT COUNT(*) AS neg_cnt FROM ZZ_输出表 WHERE UnitCost < 0, assertion: neg_cnt == 0
- 借贷平衡: SELECT SUM(Debit) AS d, SUM(Credit) AS c FROM ..., assertion: abs(d - c) < 0.01
"""


SP_TEMPLATE = """-- ========================================
-- 功能：{description}
-- 作者：AI Agent (auto-generated)
-- 依赖：{dependencies}
-- 输出表：{output_table}
-- ========================================

/*
业务逻辑说明:
{business_logic}
*/

CREATE PROCEDURE [dbo].[{name}]
{parameter_block}
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        BEGIN TRANSACTION;

        -- ========================================
        -- Step 1: [业务逻辑 - 由 AI 生成具体代码]
        {implementation}

        -- ========================================

        COMMIT TRANSACTION;

        -- 执行日志
        INSERT INTO ZZ_SP_LOG (SPName, Status, ExecTime)
        VALUES ('{name}', 'SUCCESS', GETDATE());

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;

        INSERT INTO ZZ_SP_LOG (SPName, Status, ErrorMsg, ExecTime)
        VALUES ('{name}', 'FAILED', ERROR_MESSAGE(), GETDATE());

        THROW;
    END CATCH
END
GO
"""


def _clean_implementation_body(body: str) -> str:
    """Post-process LLM-generated implementation body to remove problematic patterns.

    The template (SP_TEMPLATE) already provides:
      - CREATE PROCEDURE header and parameters
      - BEGIN / SET NOCOUNT ON
      - BEGIN TRY / BEGIN TRANSACTION ... COMMIT TRANSACTION / END TRY
      - BEGIN CATCH ... END CATCH / END
      - Trailing GO

    So the implementation body should contain ONLY the business logic between
    BEGIN TRANSACTION and COMMIT TRANSACTION. This function strips out any
    duplicate wrappers that the LLM might have included despite instructions.
    """
    # 1. Remove all GO batch separators (standalone lines)
    body = re.sub(r'^\s*GO\s*$', '', body, flags=re.IGNORECASE | re.MULTILINE)

    # 2. Remove CREATE PROCEDURE ... AS BEGIN if LLM included a full SP wrapper
    # This handles cases where the LLM ignores the "don't include header" instruction
    _had_create_proc = bool(re.search(
        r'^\s*CREATE\s+PROCEDURE\s+',
        body,
        flags=re.IGNORECASE | re.MULTILINE,
    ))
    body = re.sub(
        r'^\s*CREATE\s+PROCEDURE\s+.*?^BEGIN\s*$',
        '', body,
        flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )

    # 3. Remove SET NOCOUNT ON (already in template)
    body = re.sub(r'^\s*SET\s+NOCOUNT\s+ON\s*;?\s*$', '', body, flags=re.IGNORECASE | re.MULTILINE)

    # 4. Remove outermost BEGIN TRY / END TRY ... BEGIN CATCH / END CATCH wrapper
    #    but keep the content inside BEGIN TRY
    try_match = re.match(
        r'\s*BEGIN\s+TRY\s*\n(.*?)\n\s*END\s+TRY\s*\n\s*BEGIN\s+CATCH\s*\n.*?END\s+CATCH',
        body, flags=re.IGNORECASE | re.DOTALL,
    )
    if try_match:
        body = try_match.group(1)

    # 5. Remove outermost BEGIN TRANSACTION / COMMIT TRANSACTION wrapper
    #    but keep content between them
    trans_match = re.match(
        r'\s*BEGIN\s+TRANSACTION\s*;?\s*\n(.*?)\n\s*COMMIT\s+TRANSACTION\s*;?\s*$',
        body, flags=re.IGNORECASE | re.DOTALL,
    )
    if trans_match:
        body = trans_match.group(1)

    # 6. Remove trailing END only if we stripped a CREATE PROCEDURE wrapper (step 2)
    #    This END is the outer procedure's closing END and conflicts with the template.
    #    Do NOT remove trailing END otherwise — it may be a legitimate IF...BEGIN...END.
    if _had_create_proc:
        body = re.sub(r'\n\s*END\s*;?\s*$', '', body, flags=re.IGNORECASE)

    # 7. Remove ROLLBACK / re-THROW blocks that duplicate the template's CATCH
    body = re.sub(
        r'^\s*IF\s+@@TRANCOUNT\s*>\s*0\s*\n\s*ROLLBACK\s+TRANSACTION\s*;?\s*$',
        '', body, flags=re.IGNORECASE | re.MULTILINE,
    )

    # 8. Remove any INSERT INTO ZZ_SP_LOG statements (template already handles logging)
    body = re.sub(
        r'^\s*INSERT\s+INTO\s+ZZ_SP_LOG\s*\(.*?\)\s*VALUES\s*\(.*?\)\s*;?\s*$',
        '', body, flags=re.IGNORECASE | re.MULTILINE,
    )
    # Also handle multi-line INSERT INTO ZZ_SP_LOG
    body = re.sub(
        r'^\s*INSERT\s+INTO\s+ZZ_SP_LOG\s*\([^)]*\)\s*\n\s*VALUES\s*\([^)]*\)\s*;?\s*$',
        '', body, flags=re.IGNORECASE | re.MULTILINE,
    )

    # 9. Remove THROW statements that duplicate the template's CATCH
    body = re.sub(r'^\s*THROW\s*;?\s*$', '', body, flags=re.IGNORECASE | re.MULTILINE)

    # Clean up excessive blank lines
    body = re.sub(r'\n{3,}', '\n\n', body)

    return body.strip()


def build_sp_implementation_prompt(spec: SPSpec, schema_context: str) -> str:
    """构建单个 SP 实现代码生成的 prompt."""
    deps_desc = ""
    if spec.dependencies:
        deps_desc = "\n".join(f"  - {d}: 前置存储过程，已提供所需数据" for d in spec.dependencies)
    else:
        deps_desc = "  无依赖，本 SP 是执行链的起点"

    params_desc = ""
    if spec.parameters:
        params_desc = "\n".join(
            f"  - @{k.replace('@', '')}: {v}" for k, v in spec.parameters.items()
        )
    else:
        params_desc = "  仅 @Debug BIT = 0"

    return f"""你是一位资深的 SAP Business One T-SQL 开发专家，需要为以下存储过程编写完整的生产级实现代码。

# 数据库 Schema
{schema_context}

# 存储过程规格

**名称**: {spec.name}
**功能描述**: {spec.description}
**依赖的前置 SP**:
{deps_desc}
**输出表**: {spec.output_table or '无（仅执行运算或更新）'}
**参数**:
{params_desc}

**详细业务逻辑**:
{spec.business_logic}

# SAP B1 T-SQL 编码规范
- 使用 SAP B1 标准表关联（如 ORDR.DocEntry = RDR1.DocEntry）
- 日期字段使用 SQL Server 函数（DATEADD, DATEDIFF, GETDATE, EOMONTH）
- 对可能为 NULL 的数值字段使用 ISNULL(Field, 0)
- 金额计算使用 ROUND(..., 2) 保留两位小数
- 所有单据过滤 CANCELED = 'N'
- 使用 TOP 限制大批量操作的行数
- 临时结果考虑写入 @output_table 指定的中间表（ZZ_ 前缀）
- 包含事务控制（BEGIN/COMMIT/ROLLBACK TRANSACTION）
- 使用 BEGIN TRY...BEGIN CATCH 错误处理
- 支持 @Debug 参数控制调试输出
- 关键步骤添加注释

# 要求
1. 只输出 T-SQL 实现体（BEGIN TRANSACTION 到 COMMIT TRANSACTION 之间的代码）
2. 不要包含 CREATE PROCEDURE 头部、参数声明、或最外层的 BEGIN/END 包装
3. 不要包含 BEGIN TRY/BEGIN CATCH 错误处理（模板已提供）
4. 不要包含 INSERT INTO ZZ_SP_LOG 日志记录（模板已提供）
5. 代码要可以直接嵌入存储过程模板中
6. 使用具体的表名和字段名，不要使用占位符
7. 每个查询步骤添加清晰的注释
"""


def generate_sp_implementation(
    spec: SPSpec,
    schema_context: str,
    api_key: str,
    model: str = "deepseek-chat",
    base_url: str = "https://api.deepseek.com",
) -> str:
    """调用 LLM 为单个 SP 生成完整的 T-SQL 实现体.

    Args:
        spec: 存储过程规格（含 business_logic）
        schema_context: 预构建的 Schema 上下文字符串
        api_key: DeepSeek API Key
        model: 使用的模型 ID
        base_url: API Base URL

    Returns:
        生成的 T-SQL 实现代码；失败时返回带 TODO 的骨架注释。
    """
    prompt = build_sp_implementation_prompt(spec, schema_context)

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            max_tokens=3000,
            temperature=0.1,
            messages=[{"role": "user", "content": prompt}],
        )

        body = response.choices[0].message.content.strip()

        # 后处理：去掉可能的 markdown 代码块包裹
        if body.startswith("```"):
            # 找到第一个换行后的内容
            first_nl = body.find("\n")
            if first_nl != -1:
                body = body[first_nl + 1:]
            if body.endswith("```"):
                body = body[:-3]
            body = body.strip()

        if not body:
            raise ValueError("LLM returned empty implementation body")

        # Post-process: remove duplicate wrappers and GO statements
        body = _clean_implementation_body(body)

        if not body:
            raise ValueError("LLM implementation body is empty after cleanup")

        logger.info(f"Generated implementation for {spec.name} ({len(body)} chars)")
        return body

    except Exception as e:
        logger.error(f"SP implementation generation failed for {spec.name}: {e}")
        # 回退：返回基于 business_logic 的详细骨架注释
        logic_lines = spec.business_logic.strip().split("\n")
        fallback_lines = [
            f"-- WARNING: 自动代码生成失败 ({e})",
            f"-- 以下是基于业务逻辑的手动实现指南:",
            f"",
        ]
        for line in logic_lines:
            fallback_lines.append(f"-- {line}")
        fallback_lines.append(f"")
        fallback_lines.append(f"-- [请根据以上业务逻辑手动编写 T-SQL 实现]")
        fallback_lines.append(f"IF @Debug = 1 PRINT 'Debug: {spec.name} started (skeleton)';")
        return "\n".join(fallback_lines)


def build_repair_prompt(
    spec: SPSpec,
    current_code: str,
    failed_checks: list[dict],
    schema_context: str,
) -> str:
    """构建 AI 自修复的 prompt — 把失败的业务对账断言 + 实际值反馈给 LLM."""
    failure_lines = []
    for i, fc in enumerate(failed_checks, 1):
        actual = fc.get("actual_values") or {}
        actual_str = ", ".join(f"{k}={v}" for k, v in actual.items()) or "（无返回值）"
        failure_lines.append(
            f"{i}. 检查名称: {fc.get('name', '')}\n"
            f"   业务规则: {fc.get('description', '')}\n"
            f"   对账 SQL: {fc.get('check_sql', '')}\n"
            f"   期望条件(assertion): {fc.get('assertion', '')}\n"
            f"   实际返回值: {actual_str}\n"
            f"   失败原因: {fc.get('detail', '')}"
        )
    failures_text = "\n\n".join(failure_lines)

    return f"""你是一位资深的 SAP Business One T-SQL 专家。你之前生成的存储过程运行后，业务对账验证**未通过**，需要你修正实现代码。

# 数据库 Schema
{schema_context}

# 存储过程规格
**名称**: {spec.name}
**功能描述**: {spec.description}
**输出表**: {spec.output_table or '无'}
**业务逻辑**:
{spec.business_logic}

# 当前存储过程完整代码
```sql
{current_code}
```

# 业务对账验证失败详情
以下断言未通过，说明 SP 计算出的数据与业务预期不符:

{failures_text}

# 修复要求
1. 仔细分析每条失败断言的"期望条件"和"实际返回值"，定位业务逻辑错误（如关联条件、过滤条件、聚合口径、NULL处理、金额精度等）
2. 只输出修正后的 T-SQL 实现体（BEGIN TRANSACTION 到 COMMIT TRANSACTION 之间的业务逻辑代码）
3. 不要包含 CREATE PROCEDURE 头部、参数声明、最外层 BEGIN/END、BEGIN TRY/CATCH、INSERT INTO ZZ_SP_LOG（模板已提供）
4. 使用具体表名字段名，不要占位符
5. 针对失败的对账项做出实质性修正，不要只改注释
"""


def regenerate_sp_with_feedback(
    spec: SPSpec,
    current_code: str,
    failed_checks: list[dict],
    schema_context: str,
    api_key: str,
    model: str = "deepseek-chat",
    base_url: str = "https://api.deepseek.com",
) -> str:
    """基于失败的业务对账断言，让 LLM 重新生成修正后的 SP 实现体.

    Args:
        spec: 存储过程规格
        current_code: 当前完整 SP 代码
        failed_checks: 失败断言列表（含 name/description/check_sql/assertion/actual_values/detail）
        schema_context: Schema 上下文
        api_key: LLM API Key
        model: 模型 ID
        base_url: API Base URL

    Returns:
        修正后的 T-SQL 实现体（已清理包装）

    Raises:
        异常时向上抛出，由调用方处理。
    """
    prompt = build_repair_prompt(spec, current_code, failed_checks, schema_context)

    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        max_tokens=3000,
        temperature=0.1,
        messages=[{"role": "user", "content": prompt}],
    )

    body = response.choices[0].message.content.strip()

    # 去掉 markdown 代码块包裹
    if body.startswith("```"):
        first_nl = body.find("\n")
        if first_nl != -1:
            body = body[first_nl + 1:]
        if body.endswith("```"):
            body = body[:-3]
        body = body.strip()

    if not body:
        raise ValueError("LLM 修复返回空内容")

    body = _clean_implementation_body(body)
    if not body:
        raise ValueError("修复后的实现体清理后为空")

    logger.info(f"Regenerated implementation for {spec.name} ({len(body)} chars)")
    return body


def generate_sp_code(spec: SPSpec, implementation_body: str = "") -> str:
    """根据 SP 规格生成完整 T-SQL 代码."""
    # 构建参数块
    params = dict(spec.parameters)
    params.setdefault("@Debug", "BIT = 0")
    param_lines = [f"    @{k.replace('@', '')} {v}," for k, v in params.items()]
    param_block = "\n".join(param_lines).rstrip(",")

    dependencies = ", ".join(spec.dependencies) if spec.dependencies else "无"
    output_table = spec.output_table or "无"

    body = implementation_body if implementation_body else (
        f"-- TODO: 根据以下业务逻辑实现具体代码\n"
        f"-- {spec.business_logic}\n"
        f"\n    -- 示例: SELECT @Debug AS DebugMode;\n"
        f"    IF @Debug = 1 PRINT 'Debug: {spec.name} started';\n"
        f"\n    -- [在此处编写业务逻辑]\n"
    )

    return SP_TEMPLATE.format(
        name=spec.name,
        description=spec.description,
        dependencies=dependencies,
        output_table=output_table,
        business_logic=spec.business_logic,
        parameter_block=param_block,
        implementation=body,
    )


def generate_sp_architecture(
    user_input: str,
    schema_context: str,
    api_key: str,
    model: str = "deepseek-chat",
    base_url: str = "https://api.deepseek.com",
) -> SPArchitectureResult:
    """调用 DeepSeek API 生成存储过程体系架构设计.

    Args:
        user_input: 用户需求描述
        schema_context: 预构建的 Schema 上下文字符串
        api_key: DeepSeek API Key
        model: 使用的模型 ID
        base_url: API Base URL

    Returns:
        SPArchitectureResult: 包含解析后的架构或错误信息
    """
    prompt = build_sp_design_prompt(user_input, schema_context)

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            max_tokens=4000,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = response.choices[0].message.content

        # 三层 JSON 解析回退
        data: dict | None = None
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            # 从 markdown 代码块中提取
            json_block_match = re.search(
                r'```(?:json)?\s*\n?(\{.*?\n?\})\s*\n?```',
                response_text,
                re.DOTALL,
            )
            if json_block_match:
                try:
                    data = json.loads(json_block_match.group(1))
                except json.JSONDecodeError:
                    data = None

            # 扫描平衡大括号
            if data is None:
                data = _extract_json_balanced(response_text)

        if data is None:
            raise ValueError(
                f"Cannot parse AI response as JSON: {response_text[:500]}"
            )

        # 验证必需字段
        name = (data.get("name") or "").strip()
        description = (data.get("description") or "").strip()
        design_notes = (data.get("design_notes") or "").strip()
        raw_procedures = data.get("procedures") or []

        if not name:
            raise ValueError("AI response missing required field: 'name'")
        if not isinstance(raw_procedures, list) or len(raw_procedures) == 0:
            raise ValueError(
                "AI response missing required field: 'procedures' (must be non-empty list)"
            )

        # 转换为 SPSpec 列表
        procedures: list[SPSpec] = []
        for p in raw_procedures:
            if not isinstance(p, dict):
                continue
            spec = SPSpec(
                name=(p.get("name") or "").strip(),
                description=(p.get("description") or "").strip(),
                dependencies=p.get("dependencies") or [],
                output_table=(p.get("output_table") or "").strip(),
                parameters=p.get("parameters") or {},
                business_logic=(p.get("business_logic") or "").strip(),
                verification_checks=_normalize_checks(p.get("verification_checks")),
            )
            if not spec.name:
                continue
            procedures.append(spec)

        if not procedures:
            raise ValueError("No valid procedures found in AI response")

        architecture = SPArchitecture(
            name=name,
            description=description,
            procedures=procedures,
            design_notes=design_notes,
        )

        # 验证执行顺序（检测循环依赖）
        try:
            _ = architecture.execution_order
        except ValueError as e:
            return SPArchitectureResult(
                architecture=None,
                success=False,
                error=f"依赖关系验证失败: {e}",
            )

        logger.info(
            f"Generated SP architecture '{name}' with {len(procedures)} procedures"
        )
        return SPArchitectureResult(
            architecture=architecture,
            success=True,
        )

    except Exception as e:
        logger.error(f"SP architecture generation failed: {e}")
        return SPArchitectureResult(
            architecture=None,
            success=False,
            error=str(e),
        )
