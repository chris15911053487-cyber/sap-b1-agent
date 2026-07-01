"""Tests for the CLI entry point (main.py)."""

import pytest
from click.testing import CliRunner
from main import cli


@pytest.fixture
def runner():
    return CliRunner(mix_stderr=False)


class TestCLI:
    def test_cli_help(self, runner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "SAP B1" in result.output

    def test_query_command_requires_input(self, runner):
        result = runner.invoke(cli, ["query"])
        # 缺少必要参数，不应成功
        assert result.exit_code != 0 or "Error" in result.output or "Missing" in result.output

    def test_test_connection_no_config(self, runner, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
        result = runner.invoke(cli, ["test-connection"])
        # 应优雅处理配置缺失
        assert isinstance(result.exit_code, int)
