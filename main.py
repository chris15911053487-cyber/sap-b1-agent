#!/usr/bin/env python3
"""SAP Business One 数据库 AI 智能体 — CLI 入口."""

from __future__ import annotations

import logging
import os
import sys

import click
from dotenv import load_dotenv

from config.loader import load_config
from agent.core import DBAgent

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            os.path.join(os.path.dirname(__file__), "logs", "execution.log"),
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), "config", "config.yaml"
)


def _get_agent(config_path: str | None = None) -> DBAgent:
    """初始化 Agent，从配置文件和环境变量加载设置."""
    path = config_path or DEFAULT_CONFIG_PATH
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise click.UsageError(
            "DEEPSEEK_API_KEY 环境变量未设置。\n"
            "请在 .env 文件中设置或通过环境变量导出:\n"
            "  export DEEPSEEK_API_KEY=sk-..."
        )
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

    try:
        config = load_config(path)
    except FileNotFoundError:
        click.echo(
            f"⚠️  配置文件未找到: {path}\n"
            f"将以默认配置运行（无数据库连接）。"
        )
        from config.loader import AppConfig
        config = AppConfig()

    return DBAgent(config=config, api_key=api_key, base_url=base_url)


@click.group()
@click.version_option(version="0.1.0", prog_name="sap-b1-db-agent")
def cli():
    """SAP B1 数据库 AI 智能体 — 自然语言驱动的数据库操作工具."""


@cli.command()
@click.option(
    "--config", "-c",
    default=None,
    help="配置文件路径（默认: config/config.yaml）",
)
def interactive(config):
    """进入交互式对话模式."""
    click.echo("=" * 60)
    click.echo("  SAP B1 数据库 AI 智能体")
    click.echo("  输入 'help' 查看帮助 | 'quit' 退出")
    click.echo("=" * 60)
    click.echo()

    try:
        agent = _get_agent(config)
        click.echo("✅ Agent 已就绪")
    except click.UsageError as e:
        click.echo(f"❌ {e}")
        return

    while True:
        try:
            user_input = click.prompt("\n📝 你", prompt_suffix=" > ").strip()
        except (KeyboardInterrupt, EOFError):
            click.echo("\n👋 再见!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "q", "退出"):
            click.echo("👋 再见!")
            break

        if user_input.lower() == "help":
            click.echo("""
可用命令:
  query   - 自然语言查询
  sp      - 构建存储过程
  verify  - 数据验证
  help    - 显示此帮助
  quit    - 退出

示例:
  > 查一下物料A001的库存分布
  > 帮我创建一套成本核算的存储过程
  > 验证6月份库存数据准确性
""")
            continue

        click.echo()
        response = agent.process(user_input)
        click.echo(response.explanation)

        if response.sql:
            click.echo()
            click.echo("```sql")
            click.echo(response.sql)
            click.echo("```")

        if response.data_table:
            click.echo()
            click.echo(response.data_table)

        if response.error:
            click.echo(f"\n❌ 错误: {response.error}")


@cli.command()
@click.argument("question", required=True)
@click.option("--config", "-c", default=None, help="配置文件路径")
@click.option("--no-execute", is_flag=True, help="仅生成 SQL，不执行")
def query(question: str, config: str | None, no_execute: bool):
    """执行自然语言查询.

    \b
    示例:
      sap-b1-db-agent query "查一下上个月销售额前10的客户"
      sap-b1-db-agent query --no-execute "所有未交货的销售订单"
    """
    agent = _get_agent(config)
    response = agent.process(question, no_execute=no_execute)

    if not response.success:
        click.echo(f"❌ {response.error}")
        sys.exit(1)

    if response.sql:
        click.echo("\n📄 生成的 SQL:")
        click.echo("-" * 40)
        click.echo(response.sql)

    if response.data_table:
        click.echo("\n📊 查询结果:")
        click.echo("-" * 40)
        click.echo(response.data_table)

    if response.explanation:
        click.echo(f"\n💡 {response.explanation}")


@cli.command()
@click.option("--config", "-c", default=None, help="配置文件路径")
@click.option("--db", "-d", default=None, help="要测试的数据库名称（默认: 配置中的 default_db）")
def test_connection(config: str | None, db: str | None):
    """测试数据库连接."""
    path = config or DEFAULT_CONFIG_PATH

    try:
        cfg = load_config(path)
    except FileNotFoundError:
        click.echo(f"❌ 配置文件未找到: {path}")
        sys.exit(1)

    db_name = db or cfg.agent.default_db
    db_config = cfg.databases.get(db_name)

    if not db_config:
        click.echo(f"❌ 数据库中未配置 '{db_name}'")
        available = ", ".join(cfg.databases.keys()) if cfg.databases else "无"
        click.echo(f"可用的数据库: {available}")
        sys.exit(1)

    from database.connector import create_connection, test_connection as test_conn

    click.echo(f"🔌 测试连接: {db_config.host}:{db_config.port}/{db_config.database}")
    conn = create_connection(db_config)

    if test_conn(conn):
        click.echo(f"✅ 连接成功: {db_config.type} @ {db_config.host}")
    else:
        click.echo(f"❌ 连接失败，请检查网络和配置")
        sys.exit(1)


if __name__ == "__main__":
    cli()
