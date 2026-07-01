# agent/verifier.py
from __future__ import annotations

import logging
from dataclasses import dataclass, field

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
