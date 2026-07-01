# tests/test_config.py
import pytest
import yaml
from config.loader import load_config, AppConfig, DatabaseConfig


def test_load_valid_config(temp_config_dir):
    config_data = {
        "databases": {
            "test": {
                "type": "sql_server",
                "host": "192.168.1.100",
                "port": 1433,
                "database": "SBO_TestDB",
                "username": "sa",
                "password": "secret",
                "timeout": 30,
            }
        },
        "agent": {
            "default_db": "test",
            "model": "deepseek-chat",
            "max_query_rows": 1000,
            "log_level": "INFO",
            "locale": "zh_CN",
        },
    }
    config_path = temp_config_dir / "config.yaml"
    config_path.write_text(yaml.dump(config_data))

    cfg = load_config(str(config_path))

    assert cfg.agent.default_db == "test"
    assert cfg.agent.model == "deepseek-chat"
    assert cfg.databases["test"].host == "192.168.1.100"
    assert cfg.databases["test"].port == 1433


def test_load_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/config.yaml")


def test_load_config_with_env_var_substitution(temp_config_dir, monkeypatch):
    monkeypatch.setenv("DB_PASSWORD", "from_env")
    config_data = {
        "databases": {
            "test": {
                "type": "sql_server",
                "host": "localhost",
                "port": 1433,
                "database": "SBO_TestDB",
                "username": "sa",
                "password": "${DB_PASSWORD}",
                "timeout": 30,
            }
        },
        "agent": {
            "default_db": "test",
            "model": "deepseek-chat",
            "max_query_rows": 1000,
            "log_level": "INFO",
            "locale": "zh_CN",
        },
    }
    config_path = temp_config_dir / "config.yaml"
    config_path.write_text(yaml.dump(config_data))

    cfg = load_config(str(config_path))
    assert cfg.databases["test"].password == "from_env"
