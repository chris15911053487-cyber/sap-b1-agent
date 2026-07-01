"""表结构查询 API."""
from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from database.schema import get_core_tables

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["schema"])


class ColumnInfo(BaseModel):
    name: str
    data_type: str
    is_nullable: bool
    is_primary_key: bool
    description: str


class TableInfo(BaseModel):
    name: str
    description: str
    column_count: int
    columns: list[dict]


@router.get("/schema/tables", response_model=list[TableInfo])
async def list_tables():
    """获取系统已知的 SAP B1 核心表结构列表."""
    core_tables = get_core_tables()

    result = []
    for table_name, schema in core_tables.items():
        columns = []
        for col in schema.columns:
            columns.append({
                "name": col.name,
                "data_type": col.data_type,
                "is_nullable": col.is_nullable,
                "is_primary_key": col.is_primary_key,
                "description": col.description or "",
            })

        result.append({
            "name": table_name,
            "description": schema.description,
            "column_count": len(schema.columns),
            "columns": columns,
        })

    # Sort by name for stable output
    result.sort(key=lambda t: t["name"])
    return result
