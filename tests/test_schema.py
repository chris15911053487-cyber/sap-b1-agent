import pytest
from database.schema import (
    TableSchema,
    ColumnInfo,
    SchemaCache,
    get_core_tables,
    get_related_tables,
)


class TestColumnInfo:
    def test_creates_column_info(self):
        col = ColumnInfo(
            name="ItemCode",
            data_type="nvarchar",
            max_length=20,
            is_nullable=False,
            is_primary_key=True,
        )
        assert col.name == "ItemCode"
        assert col.data_type == "nvarchar"
        assert col.is_primary_key is True


class TestTableSchema:
    def test_creates_table_schema(self):
        schema = TableSchema(
            table_name="OITM",
            description="物料主数据",
            columns=[
                ColumnInfo("ItemCode", "nvarchar", 20, False, True),
                ColumnInfo("ItemName", "nvarchar", 100, False, False),
                ColumnInfo("OnHand", "numeric", None, True, False),
            ],
        )
        assert schema.table_name == "OITM"
        assert len(schema.columns) == 3
        assert schema.get_column("ItemCode").is_primary_key is True
        assert schema.get_column("NonExistent") is None


class TestGetCoreTables:
    def test_returns_known_core_tables(self):
        tables = get_core_tables()
        assert "OITM" in tables
        assert "ORDR" in tables
        assert "OCRD" in tables
        assert tables["OITM"].description == "物料主数据"
        assert tables["ORDR"].description == "销售订单"


class TestSchemaCache:
    def test_add_and_get(self):
        cache = SchemaCache()
        schema = TableSchema(table_name="TestTable", description="测试表", columns=[])
        cache.add(schema)
        assert cache.get("TestTable") is schema
        assert cache.get("NonExistent") is None

    def test_has_checks_existence(self):
        cache = SchemaCache()
        schema = TableSchema(table_name="OITM", description="物料", columns=[])
        cache.add(schema)
        assert cache.has("OITM") is True
        assert cache.has("UNKNOWN") is False


class TestRelatedTables:
    def test_returns_related_for_known_table(self):
        related = get_related_tables("ORDR")
        assert "RDR1" in related
        assert "OCRD" in related
        assert "OITM" in related

    def test_returns_empty_for_unknown_table(self):
        related = get_related_tables("UNKNOWN_TABLE")
        assert related == []
