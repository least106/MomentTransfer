import logging
import sqlite3
import sys

import click

from src.format_registry import delete_mapping, init_db, list_mappings, register_mapping


@click.group()
def registry():
    """管理 format registry（SQLite）"""
    pass


@registry.command("list")
@click.argument("db_path", required=True)
def list_cmd(db_path):
    """列出 registry 中的所有映射"""
    try:
        init_db(db_path)
        items = list_mappings(db_path)
        if not items:
            click.echo("（空）")
            return
        for m in items:
            click.echo(
                f"[{m['id']}] {m['pattern']} -> {m['format_path']}  (added: {m['added_at']})"
            )
    except (sqlite3.Error, FileNotFoundError, PermissionError) as e:
        click.echo(f"数据库错误: {e}")
        logging.exception("Registry list failed")
        sys.exit(2)
    except Exception as e:
        # 捕获意外错误并记录完整 traceback 以便排查
        logging.exception("Unexpected error while listing registry mappings")
        click.echo(f"未知错误: {e}; 详情已记录到日志")
        sys.exit(3)


@registry.command("register")
@click.argument("db_path", required=True)
@click.argument("pattern", required=True)
@click.argument("format_path", required=True)
def register_cmd(db_path, pattern, format_path):
    """注册一条映射: PATTERN -> FORMAT_PATH"""
    try:
        init_db(db_path)
        register_mapping(db_path, pattern, format_path)
        click.echo("已注册")
    except (ValueError, sqlite3.Error, FileNotFoundError, PermissionError) as e:
        click.echo(f"错误: {e}")
        logging.exception("Registry register failed")
        sys.exit(2)
    except Exception as e:
        logging.exception("Unexpected error while registering mapping")
        click.echo(f"未知错误: {e}; 详情已记录到日志")
        sys.exit(3)


@registry.command("remove")
@click.argument("db_path", required=True)
@click.argument("id", type=int, required=True)
def remove_cmd(db_path, id):
    """按 ID 删除映射"""
    try:
        init_db(db_path)
        delete_mapping(db_path, id)
        click.echo("已删除")
    except (KeyError, sqlite3.Error, FileNotFoundError, PermissionError) as e:
        click.echo(f"错误: {e}")
        logging.exception("Registry remove failed")
        sys.exit(2)
    except Exception as e:
        logging.exception("Unexpected error while removing mapping")
        click.echo(f"未知错误: {e}; 详情已记录到日志")
        sys.exit(3)


if __name__ == "__main__":
    registry()
