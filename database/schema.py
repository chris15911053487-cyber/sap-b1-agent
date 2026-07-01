from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ColumnInfo:
    name: str
    data_type: str
    max_length: Optional[int] = None
    is_nullable: bool = True
    is_primary_key: bool = False
    description: str = ""


@dataclass
class TableSchema:
    table_name: str
    description: str
    columns: list[ColumnInfo] = field(default_factory=list)
    relations: list[TableRelation] = field(default_factory=list)

    def get_column(self, name: str) -> Optional[ColumnInfo]:
        for col in self.columns:
            if col.name.lower() == name.lower():
                return col
        return None


@dataclass
class TableRelation:
    target_table: str
    join_condition: str
    relation_type: str = "INNER"  # INNER, LEFT, etc.
    description: str = ""


class SchemaCache:
    def __init__(self):
        self._cache: dict[str, TableSchema] = {}

    def add(self, schema: TableSchema) -> None:
        self._cache[schema.table_name.upper()] = schema

    def get(self, table_name: str) -> Optional[TableSchema]:
        return self._cache.get(table_name.upper())

    def has(self, table_name: str) -> bool:
        return table_name.upper() in self._cache

    def list_tables(self) -> list[str]:
        return sorted(self._cache.keys())


# ============================================================
# SAP B1 核心表结构（内嵌知识）
# ============================================================

def get_core_tables() -> dict[str, TableSchema]:
    """返回 SAP B1 核心表结构定义."""
    return {

        # === 销售模块 ===
        "ORDR": TableSchema(
            table_name="ORDR",
            description="销售订单",
            columns=[
                ColumnInfo("DocEntry", "int", is_primary_key=True, description="单据内码"),
                ColumnInfo("DocNum", "int", description="单据编号"),
                ColumnInfo("DocDate", "datetime", description="过账日期"),
                ColumnInfo("DocDueDate", "datetime", description="交货日期"),
                ColumnInfo("CardCode", "nvarchar", 15, description="客户代码"),
                ColumnInfo("CardName", "nvarchar", 100, description="客户名称"),
                ColumnInfo("DocTotal", "numeric", description="单据总金额"),
                ColumnInfo("CANCELED", "char", 1, description="取消标记 Y/N"),
                ColumnInfo("DocStatus", "char", 1, description="单据状态 O/C"),
            ],
            relations=[
                TableRelation("RDR1", "ORDR.DocEntry = RDR1.DocEntry", "INNER", "订单行"),
                TableRelation("OCRD", "ORDR.CardCode = OCRD.CardCode", "INNER", "客户"),
            ],
        ),
        "RDR1": TableSchema(
            table_name="RDR1",
            description="销售订单行",
            columns=[
                ColumnInfo("DocEntry", "int", description="单据内码"),
                ColumnInfo("LineNum", "int", description="行号"),
                ColumnInfo("ItemCode", "nvarchar", 20, description="物料代码"),
                ColumnInfo("Dscription", "nvarchar", 100, description="物料描述"),
                ColumnInfo("Quantity", "numeric", description="数量"),
                ColumnInfo("Price", "numeric", description="单价"),
                ColumnInfo("LineTotal", "numeric", description="行总金额"),
            ],
            relations=[
                TableRelation("ORDR", "RDR1.DocEntry = ORDR.DocEntry", "INNER", "订单头"),
                TableRelation("OITM", "RDR1.ItemCode = OITM.ItemCode", "INNER", "物料"),
            ],
        ),
        "OINV": TableSchema(
            table_name="OINV",
            description="AR发票（销售发票）",
            columns=[
                ColumnInfo("DocEntry", "int", is_primary_key=True, description="单据内码"),
                ColumnInfo("DocNum", "int", description="单据编号"),
                ColumnInfo("DocDate", "datetime", description="过账日期"),
                ColumnInfo("CardCode", "nvarchar", 15, description="客户代码"),
                ColumnInfo("CardName", "nvarchar", 100, description="客户名称"),
                ColumnInfo("DocTotal", "numeric", description="发票总金额"),
                ColumnInfo("PaidToDate", "numeric", description="已收款金额"),
                ColumnInfo("CANCELED", "char", 1, description="取消标记"),
            ],
            relations=[
                TableRelation("INV1", "OINV.DocEntry = INV1.DocEntry", "INNER", "发票行"),
                TableRelation("OCRD", "OINV.CardCode = OCRD.CardCode", "INNER", "客户"),
            ],
        ),
        "INV1": TableSchema(
            table_name="INV1",
            description="AR发票行",
            columns=[
                ColumnInfo("DocEntry", "int", description="单据内码"),
                ColumnInfo("LineNum", "int", description="行号"),
                ColumnInfo("ItemCode", "nvarchar", 20, description="物料代码"),
                ColumnInfo("Quantity", "numeric", description="数量"),
                ColumnInfo("Price", "numeric", description="单价"),
                ColumnInfo("LineTotal", "numeric", description="行总金额"),
                ColumnInfo("Cost", "numeric", description="成本"),
            ],
            relations=[
                TableRelation("OINV", "INV1.DocEntry = OINV.DocEntry", "INNER", "发票头"),
                TableRelation("OITM", "INV1.ItemCode = OITM.ItemCode", "INNER", "物料"),
            ],
        ),

        # === 采购模块 ===
        "OPOR": TableSchema(
            table_name="OPOR",
            description="采购订单",
            columns=[
                ColumnInfo("DocEntry", "int", is_primary_key=True, description="单据内码"),
                ColumnInfo("DocNum", "int", description="单据编号"),
                ColumnInfo("DocDate", "datetime", description="过账日期"),
                ColumnInfo("CardCode", "nvarchar", 15, description="供应商代码"),
                ColumnInfo("CardName", "nvarchar", 100, description="供应商名称"),
                ColumnInfo("DocTotal", "numeric", description="单据总金额"),
                ColumnInfo("CANCELED", "char", 1, description="取消标记"),
            ],
            relations=[
                TableRelation("POR1", "OPOR.DocEntry = POR1.DocEntry", "INNER", "采购订单行"),
                TableRelation("OCRD", "OPOR.CardCode = OCRD.CardCode", "INNER", "供应商"),
            ],
        ),
        "POR1": TableSchema(
            table_name="POR1",
            description="采购订单行",
            columns=[
                ColumnInfo("DocEntry", "int", description="单据内码"),
                ColumnInfo("LineNum", "int", description="行号"),
                ColumnInfo("ItemCode", "nvarchar", 20, description="物料代码"),
                ColumnInfo("Quantity", "numeric", description="数量"),
                ColumnInfo("Price", "numeric", description="单价"),
                ColumnInfo("LineTotal", "numeric", description="行总金额"),
            ],
        ),

        # === 库存模块 ===
        "OITM": TableSchema(
            table_name="OITM",
            description="物料主数据",
            columns=[
                ColumnInfo("ItemCode", "nvarchar", 20, is_primary_key=True, description="物料代码"),
                ColumnInfo("ItemName", "nvarchar", 100, description="物料名称"),
                ColumnInfo("FrgnName", "nvarchar", 100, description="外文名称"),
                ColumnInfo("ItmsGrpCod", "int", description="物料组"),
                ColumnInfo("OnHand", "numeric", description="库存数量"),
                ColumnInfo("AvgPrice", "numeric", description="移动平均价"),
                ColumnInfo("InvntryUom", "nvarchar", 10, description="库存单位"),
                ColumnInfo("BuyUnitMsr", "nvarchar", 10, description="采购单位"),
                ColumnInfo("SalUnitMsr", "nvarchar", 10, description="销售单位"),
            ],
        ),
        "OITW": TableSchema(
            table_name="OITW",
            description="仓库库存",
            columns=[
                ColumnInfo("ItemCode", "nvarchar", 20, description="物料代码"),
                ColumnInfo("WhsCode", "nvarchar", 8, description="仓库代码"),
                ColumnInfo("OnHand", "numeric", description="在手量"),
                ColumnInfo("IsCommited", "numeric", description="已承诺量"),
                ColumnInfo("OnOrder", "numeric", description="在途量"),
            ],
            relations=[
                TableRelation("OITM", "OITW.ItemCode = OITM.ItemCode", "INNER", "物料"),
            ],
        ),

        # === 生产模块 ===
        "OWOR": TableSchema(
            table_name="OWOR",
            description="生产工单",
            columns=[
                ColumnInfo("DocEntry", "int", is_primary_key=True, description="单据内码"),
                ColumnInfo("DocNum", "int", description="工单号"),
                ColumnInfo("ItemCode", "nvarchar", 20, description="成品物料代码"),
                ColumnInfo("PlannedQty", "numeric", description="计划数量"),
                ColumnInfo("CmpltQty", "numeric", description="完成数量"),
                ColumnInfo("DueDate", "datetime", description="到期日"),
                ColumnInfo("Status", "char", 1, description="状态 P/R/C"),
            ],
            relations=[
                TableRelation("WOR1", "OWOR.DocEntry = WOR1.DocEntry", "INNER", "工单BOM行"),
                TableRelation("OITM", "OWOR.ItemCode = OITM.ItemCode", "INNER", "成品物料"),
            ],
        ),
        "WOR1": TableSchema(
            table_name="WOR1",
            description="生产工单BOM行（组件）",
            columns=[
                ColumnInfo("DocEntry", "int", description="单据内码"),
                ColumnInfo("LineNum", "int", description="行号"),
                ColumnInfo("ItemCode", "nvarchar", 20, description="组件物料代码"),
                ColumnInfo("BaseQty", "numeric", description="标准用量"),
                ColumnInfo("PlannedQty", "numeric", description="计划用量"),
                ColumnInfo("IssuedQty", "numeric", description="已发料量"),
            ],
        ),

        # === 库存交易 ===
        "OIGE": TableSchema(
            table_name="OIGE",
            description="发料单（库存发货）",
            columns=[
                ColumnInfo("DocEntry", "int", is_primary_key=True, description="单据内码"),
                ColumnInfo("DocNum", "int", description="单据编号"),
                ColumnInfo("DocDate", "datetime", description="过账日期"),
                ColumnInfo("CANCELED", "char", 1, description="取消标记"),
            ],
            relations=[
                TableRelation("IGE1", "OIGE.DocEntry = IGE1.DocEntry", "INNER", "发料行"),
            ],
        ),
        "IGE1": TableSchema(
            table_name="IGE1",
            description="发料单行",
            columns=[
                ColumnInfo("DocEntry", "int", description="单据内码"),
                ColumnInfo("LineNum", "int", description="行号"),
                ColumnInfo("ItemCode", "nvarchar", 20, description="物料代码"),
                ColumnInfo("Quantity", "numeric", description="数量"),
                ColumnInfo("Price", "numeric", description="单价"),
                ColumnInfo("BaseEntry", "int", description="源单据内码"),
                ColumnInfo("BaseType", "int", description="源单据类型"),
            ],
            relations=[
                TableRelation("OIGE", "IGE1.DocEntry = OIGE.DocEntry", "INNER", "发料头"),
                TableRelation("OWOR", "IGE1.BaseEntry = OWOR.DocEntry", "INNER", "工单(当BaseType=202)"),
                TableRelation("OITM", "IGE1.ItemCode = OITM.ItemCode", "INNER", "物料"),
            ],
        ),

        # === 财务模块 ===
        "OJDT": TableSchema(
            table_name="OJDT",
            description="日记账分录头",
            columns=[
                ColumnInfo("TransId", "int", is_primary_key=True, description="事务ID"),
                ColumnInfo("RefDate", "datetime", description="过账日期"),
                ColumnInfo("Memo", "nvarchar", 200, description="摘要"),
                ColumnInfo("TransCode", "nvarchar", 10, description="事务代码"),
            ],
            relations=[
                TableRelation("JDT1", "OJDT.TransId = JDT1.TransId", "INNER", "分录行"),
            ],
        ),
        "JDT1": TableSchema(
            table_name="JDT1",
            description="日记账分录行",
            columns=[
                ColumnInfo("TransId", "int", description="事务ID"),
                ColumnInfo("Line_ID", "int", description="行号"),
                ColumnInfo("Account", "nvarchar", 15, description="科目代码"),
                ColumnInfo("Debit", "numeric", description="借方金额"),
                ColumnInfo("Credit", "numeric", description="贷方金额"),
                ColumnInfo("FCDebit", "numeric", description="外币借方"),
                ColumnInfo("FCCredit", "numeric", description="外币贷方"),
            ],
            relations=[
                TableRelation("OJDT", "JDT1.TransId = OJDT.TransId", "INNER", "分录头"),
                TableRelation("OACT", "JDT1.Account = OACT.AcctCode", "INNER", "科目"),
            ],
        ),
        "OACT": TableSchema(
            table_name="OACT",
            description="科目表",
            columns=[
                ColumnInfo("AcctCode", "nvarchar", 15, is_primary_key=True, description="科目代码"),
                ColumnInfo("AcctName", "nvarchar", 100, description="科目名称"),
                ColumnInfo("AcctType", "char", 1, description="科目类型 A/E/I"),
                ColumnInfo("CurrTotal", "numeric", description="本币余额"),
            ],
        ),

        # === 业务伙伴 ===
        "OCRD": TableSchema(
            table_name="OCRD",
            description="业务伙伴主数据",
            columns=[
                ColumnInfo("CardCode", "nvarchar", 15, is_primary_key=True, description="BP代码"),
                ColumnInfo("CardName", "nvarchar", 100, description="BP名称"),
                ColumnInfo("CardType", "char", 1, description="类型 C/S/L"),
                ColumnInfo("Phone1", "nvarchar", 20, description="电话"),
                ColumnInfo("E_Mail", "nvarchar", 100, description="邮箱"),
                ColumnInfo("Balance", "numeric", description="余额"),
            ],
        ),
    }


# ============================================================
# 表关联关系
# ============================================================

_RELATED_TABLES_MAP: dict[str, list[str]] = {
    "ORDR": ["RDR1", "OCRD", "OITM"],
    "RDR1": ["ORDR", "OITM"],
    "OINV": ["INV1", "OCRD", "OITM"],
    "INV1": ["OINV", "OITM"],
    "OPOR": ["POR1", "OCRD", "OITM"],
    "POR1": ["OPOR", "OITM"],
    "OWOR": ["WOR1", "OITM", "OIGE", "IGE1"],
    "WOR1": ["OWOR", "OITM"],
    "OIGE": ["IGE1", "OWOR", "OITM"],
    "IGE1": ["OIGE", "OWOR", "OITM"],
    "OJDT": ["JDT1", "OACT"],
    "JDT1": ["OJDT", "OACT"],
    "OITW": ["OITM"],
}


def get_related_tables(table_name: str) -> list[str]:
    """返回与指定表关联的其他表."""
    return _RELATED_TABLES_MAP.get(table_name.upper(), [])
