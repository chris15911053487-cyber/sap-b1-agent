from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class DatabaseConfig:
    type: str                       # "sql_server" | "hana"
    host: str
    port: int
    database: str
    username: str
    password: str
    timeout: int = 30
    readonly: bool = False
    tds_version: str = "7.0"  # FreeTDS TDS 协议版本（7.0 兼容性最广）


@dataclass
class AgentConfig:
    default_db: str = "test"
    model: str = "deepseek-chat"
    max_query_rows: int = 1000
    log_level: str = "INFO"
    locale: str = "zh_CN"


@dataclass
class AppConfig:
    databases: dict[str, DatabaseConfig] = field(default_factory=dict)
    agent: AgentConfig = field(default_factory=AgentConfig)


_ENV_VAR_RE = re.compile(r"\$\{(\w+)\}")


def _resolve_env_vars(value: str) -> str:
    """替换字符串中的 ${VAR} 为环境变量值."""
    def _replace(match: re.Match) -> str:
        var_name = match.group(1)
        resolved = os.environ.get(var_name, "")
        if not resolved:
            raise ValueError(
                f"Environment variable '{var_name}' referenced in config "
                f"is not set. Set it in .env or the shell environment."
            )
        return resolved
    return _ENV_VAR_RE.sub(_replace, value)


def _resolve_dict(obj: dict) -> dict:
    """递归替换字典中所有字符串值的环境变量."""
    result = {}
    for key, value in obj.items():
        if isinstance(value, str):
            result[key] = _resolve_env_vars(value)
        elif isinstance(value, dict):
            result[key] = _resolve_dict(value)
        elif isinstance(value, list):
            result[key] = [
                _resolve_env_vars(v) if isinstance(v, str) else v
                for v in value
            ]
        else:
            result[key] = value
    return result


def load_config(path: str) -> AppConfig:
    """从 YAML 文件加载配置，支持 ${ENV_VAR} 环境变量替换."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if raw is None:
        raise ValueError(f"Config file is empty: {path}")

    raw = _resolve_dict(raw)

    databases = {}
    if "databases" in raw:
        for name, db_cfg in raw["databases"].items():
            databases[name] = DatabaseConfig(**db_cfg)

    agent_cfg = raw.get("agent", {})
    agent = AgentConfig(**agent_cfg) if agent_cfg else AgentConfig()

    return AppConfig(databases=databases, agent=agent)
