from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

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


@dataclass
class SPSpec:
    name: str
    description: str
    dependencies: list[str] = field(default_factory=list)
    output_table: str = ""
    parameters: dict[str, str] = field(default_factory=dict)
    business_logic: str = ""


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
      "business_logic": "详细的业务逻辑描述，供后续代码生成使用"
    }}
  ]
}}
"""


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
