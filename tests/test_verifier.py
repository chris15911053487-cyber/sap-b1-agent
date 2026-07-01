# tests/test_verifier.py
import pytest
from agent.verifier import (
    VerificationCheck,
    VerificationPlan,
    VerificationReport,
    VerificationFinding,
    generate_standard_inventory_checks,
)


class TestVerificationCheck:
    def test_creates_check(self):
        check = VerificationCheck(
            name="库存余额vs流水",
            description="OITW.OnHand 对比 OILM 流水汇总",
            category="库存",
            check_sql="SELECT 1 AS test",
            expected_result="两者一致",
        )
        assert check.name == "库存余额vs流水"
        assert check.category == "库存"


class TestGenerateStandardInventoryChecks:
    def test_returns_multiple_checks(self):
        checks = generate_standard_inventory_checks()
        assert len(checks) >= 3
        categories = {c.category for c in checks}
        assert "库存" in categories

    def test_each_check_has_sql(self):
        checks = generate_standard_inventory_checks()
        for check in checks:
            assert check.check_sql, f"Check '{check.name}' has no SQL"
            assert check.name
            assert check.description


class TestVerificationPlan:
    def test_creates_plan_with_checks(self):
        checks = generate_standard_inventory_checks()[:2]
        plan = VerificationPlan(
            name="月度库存验证",
            description="月度库存数据交叉验证",
            checks=checks,
        )
        assert plan.name == "月度库存验证"
        assert len(plan.checks) == 2


class TestVerificationReport:
    def test_creates_report_with_findings(self):
        findings = [
            VerificationFinding(
                check_name="库存余额检查",
                status="pass",
                detail="数据一致",
            ),
            VerificationFinding(
                check_name="负库存检查",
                status="fail",
                detail="发现3个物料的库存为负",
                affected_items=["A001", "A002", "A003"],
            ),
        ]
        report = VerificationReport(
            plan_name="库存数据验证",
            findings=findings,
        )
        assert report.total_checks == 2
        assert report.passed == 1
        assert report.failed == 1
        assert report.pass_rate == 0.5

    def test_summary_text(self):
        report = VerificationReport(
            plan_name="测试验证",
            findings=[
                VerificationFinding("C1", "pass", "OK"),
                VerificationFinding("C2", "pass", "OK"),
            ],
        )
        summary = report.summary_text()
        assert "2" in summary
        assert "100%" in summary or "通过" in summary
