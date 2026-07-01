import pytest
from unittest.mock import patch, MagicMock

from database.connector import (
    DatabaseConnection,
    create_connection,
    close_connection,
)
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


class TestCreateConnection:
    def test_creates_connection_object(self, db_config):
        conn = create_connection(db_config)
        assert isinstance(conn, DatabaseConnection)
        assert conn.config == db_config

    def test_rejects_unsupported_type(self):
        cfg = DatabaseConfig(
            type="oracle",
            host="localhost",
            port=1521,
            database="XEPDB1",
            username="scott",
            password="tiger",
        )
        with pytest.raises(ValueError, match="Unsupported"):
            create_connection(cfg)


class TestTestConnection:
    @patch("database.connector.pymssql")
    def test_returns_true_on_success(self, mock_pymssql, db_config):
        from database.connector import test_connection

        conn = create_connection(db_config)
        result = test_connection(conn)

        mock_pymssql.connect.assert_called_once_with(
            server="localhost",
            port="1433",
            user="sa",
            password="secret",
            database="SBO_TestDB",
            login_timeout=10,
            tds_version="7.0",
            as_dict=False,
        )
        assert result is True

    @patch("database.connector.pymssql")
    def test_returns_false_on_failure(self, mock_pymssql, db_config):
        from database.connector import test_connection

        mock_pymssql.connect.side_effect = Exception("Connection refused")
        conn = create_connection(db_config)
        result = test_connection(conn)
        assert result is False


class TestCloseConnection:
    def test_closes_active_connection(self, db_config):
        mock_conn = MagicMock()
        conn = create_connection(db_config)
        conn._raw_connection = mock_conn
        close_connection(conn)
        mock_conn.close.assert_called_once()

    def test_handles_none_connection(self, db_config):
        conn = create_connection(db_config)
        conn._raw_connection = None
        close_connection(conn)  # Should not raise
