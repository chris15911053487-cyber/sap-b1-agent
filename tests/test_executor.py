import pytest
from unittest.mock import patch, MagicMock

from database.executor import (
    QueryResult,
    ExecResult,
    execute_query,
    execute_statement,
    is_dangerous_sql,
)
from database.connector import create_connection
from config.loader import DatabaseConfig


@pytest.fixture
def db_config():
    return DatabaseConfig(
        type="sql_server",
        host="localhost",
        port=1433,
        database="SBO_TestDB",
        username="sa",
        password="secret",
        timeout=10,
    )


@pytest.fixture
def db_connection(db_config):
    return create_connection(db_config)


class TestDangerousSqlDetection:
    def test_detects_drop_table(self):
        assert is_dangerous_sql("DROP TABLE OITM") is True

    def test_detects_truncate(self):
        assert is_dangerous_sql("TRUNCATE TABLE OITM") is True

    def test_detects_delete_without_where(self):
        assert is_dangerous_sql("DELETE FROM OITM") is True

    def test_allows_delete_with_where(self):
        assert is_dangerous_sql("DELETE FROM OITM WHERE ItemCode='A001'") is False

    def test_allows_select(self):
        assert is_dangerous_sql("SELECT * FROM OITM") is False

    def test_allows_create_procedure(self):
        assert is_dangerous_sql(
            "CREATE PROCEDURE SP_Test AS BEGIN SELECT 1 END"
        ) is False


class TestExecuteQuery:
    @patch("database.executor.pymssql")
    def test_returns_query_result_with_rows(self, mock_pymssql, db_connection):
        mock_cursor = MagicMock()
        mock_cursor.description = [("ItemCode",), ("ItemName",)]
        mock_cursor.fetchall.return_value = [("A001", "Widget")]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pymssql.connect.return_value = mock_conn

        result = execute_query(db_connection, "SELECT ItemCode, ItemName FROM OITM")

        assert isinstance(result, QueryResult)
        assert result.columns == ["ItemCode", "ItemName"]
        assert len(result.rows) == 1
        assert result.rows[0] == ("A001", "Widget")
        assert result.row_count == 1
        assert result.success is True

    @patch("database.executor.pymssql")
    def test_applies_max_rows_limit(self, mock_pymssql, db_connection):
        mock_cursor = MagicMock()
        mock_cursor.description = [("ItemCode",)]
        mock_cursor.fetchall.return_value = [("A001",)]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pymssql.connect.return_value = mock_conn

        execute_query(db_connection, "SELECT ItemCode FROM OITM", max_rows=500)

        modified_sql = mock_cursor.execute.call_args[0][0]
        assert "TOP 500" in modified_sql

    @patch("database.executor.pymssql")
    def test_captures_errors(self, mock_pymssql, db_connection):
        mock_pymssql.connect.side_effect = Exception("Login failed")

        result = execute_query(db_connection, "SELECT * FROM OITM")

        assert result.success is False
        assert "Login failed" in result.error


class TestExecuteStatement:
    @patch("database.executor.pymssql")
    def test_executes_non_query(self, mock_pymssql, db_connection):
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 5
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pymssql.connect.return_value = mock_conn

        result = execute_statement(
            db_connection,
            "CREATE PROCEDURE SP_Test AS BEGIN SELECT 1 END",
        )

        assert result.success is True
        assert result.rows_affected == 5

    def test_rejects_dangerous_statement(self, db_connection):
        result = execute_statement(db_connection, "DROP TABLE OITM")
        assert result.success is False
        assert "dangerous" in result.error.lower()
