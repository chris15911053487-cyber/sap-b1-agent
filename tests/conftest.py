# tests/conftest.py
import pytest
import tempfile
from pathlib import Path


@pytest.fixture
def temp_config_dir():
    """创建临时配置目录用于测试."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_db_config():
    """样本数据库配置."""
    return {
        "type": "sql_server",
        "host": "localhost",
        "port": 1433,
        "database": "SBO_TestDB",
        "username": "sa",
        "password": "test_password",
        "timeout": 10,
    }


@pytest.fixture
def sample_agent_config():
    """样本 Agent 配置."""
    return {
        "default_db": "test",
        "model": "deepseek-chat",
        "max_query_rows": 1000,
        "log_level": "DEBUG",
        "locale": "zh_CN",
    }
