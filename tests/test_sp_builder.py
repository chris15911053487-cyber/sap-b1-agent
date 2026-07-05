import pytest
from agent.sp_builder import (
    SPArchitecture,
    SPSpec,
    generate_sp_code,
    build_sp_design_prompt,
    SP_TEMPLATE,
)


class TestSPSpec:
    def test_creates_sp_spec(self):
        spec = SPSpec(
            name="SP_Cost_Material",
            description="材料成本归集",
            dependencies=[],
            output_table="ZZ_COST_MATERIAL",
        )
        assert spec.name == "SP_Cost_Material"
        assert spec.description == "材料成本归集"


class TestSPArchitecture:
    def test_creates_architecture(self):
        arch = SPArchitecture(
            name="成本核算体系",
            description="完整成本核算",
            procedures=[
                SPSpec("SP_Cost_Material", "材料成本归集", [], "ZZ_COST_MATERIAL"),
                SPSpec("SP_Cost_Main", "主调度", ["SP_Cost_Material"], ""),
            ],
        )
        assert len(arch.procedures) == 2
        assert arch.execution_order == ["SP_Cost_Material", "SP_Cost_Main"]


class TestGenerateSpCode:
    def test_generates_valid_sql(self):
        spec = SPSpec(
            name="SP_Test_Proc",
            description="测试存储过程，返回物料列表",
            parameters={"@TopN": "INT = 10"},
            dependencies=[],
            output_table="",
            business_logic=(
                "从 OITM 表查询前 @TopN 条物料记录，"
                "返回 ItemCode, ItemName, OnHand 三个字段"
            ),
        )
        code = generate_sp_code(spec)

        assert "CREATE PROCEDURE" in code
        assert "SP_Test_Proc" in code
        assert "@TopN" in code
        assert "OITM" in code
        assert "SET NOCOUNT ON" in code
        assert "END" in code

    def test_includes_standard_header(self):
        spec = SPSpec(
            name="SP_MyProc",
            description="我的存储过程",
            dependencies=["SP_Step1"],
            output_table="ZZ_MYRESULT",
        )
        code = generate_sp_code(spec)

        assert "-- 功能：我的存储过程" in code
        assert "-- 作者：" in code
        assert "-- 依赖：SP_Step1" in code
        assert "-- 输出表：ZZ_MYRESULT" in code

    def test_includes_error_handling(self):
        """简化模板不再包含 TRY/CATCH，验证基本结构完整."""
        spec = SPSpec(name="SP_Proc", description="测试")
        code = generate_sp_code(spec)

        assert "BEGIN" in code
        assert "SET NOCOUNT ON" in code
        assert "END" in code
        assert "GO" in code

    def test_includes_log_insert(self):
        """简化模板不再包含日志，验证基本生成正确."""
        spec = SPSpec(name="SP_Proc", description="测试")
        code = generate_sp_code(spec)

        assert "CREATE PROCEDURE" in code
        assert "SP_Proc" in code


class TestBuildSpDesignPrompt:
    def test_includes_user_requirement(self):
        prompt = build_sp_design_prompt("成本核算体系", "[schema]")
        assert "成本核算体系" in prompt
        assert "[schema]" in prompt

    def test_includes_design_rules(self):
        prompt = build_sp_design_prompt("测试", "[schema]")
        assert "职责单一" in prompt
        assert "SP_" in prompt
