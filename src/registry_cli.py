import click
from src.format_registry import init_db, list_mappings, register_mapping, _ensure_db, delete_mapping
from pathlib import Path
import sys

@click.group()
def registry():
    """管理 format registry（SQLite）"""
    pass

@registry.command('list')
@click.argument('db_path', required=True)
def list_cmd(db_path):
    """列出 registry 中的所有映射"""
    try:
        init_db(db_path)
        items = list_mappings(db_path)
        if not items:
            click.echo('（空）')
            return
        for m in items:
            click.echo(f"[{m['id']}] {m['pattern']} -> {m['format_path']}  (added: {m['added_at']})")
    except Exception as e:
        click.echo(f"错误: {e}")
        sys.exit(2)

@registry.command('register')
@click.argument('db_path', required=True)
@click.argument('pattern', required=True)
@click.argument('format_path', required=True)
def register_cmd(db_path, pattern, format_path):
    """注册一条映射: PATTERN -> FORMAT_PATH"""
    try:
        init_db(db_path)
        register_mapping(db_path, pattern, format_path)
        click.echo('已注册')
    except Exception as e:
        click.echo(f"错误: {e}")
        sys.exit(2)

@registry.command('remove')
@click.argument('db_path', required=True)
@click.argument('id', type=int, required=True)
def remove_cmd(db_path, id):
    """按 ID 删除映射"""
    try:
        init_db(db_path)
        delete_mapping(db_path, id)
        click.echo('已删除')
    except Exception as e:
        click.echo(f"错误: {e}")
        sys.exit(2)

if __name__ == '__main__':
    registry()
