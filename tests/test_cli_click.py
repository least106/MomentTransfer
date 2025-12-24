from click.testing import CliRunner
import json
from pathlib import Path

from cli import main as cli_main


def test_cli_non_interactive(tmp_path):
    runner = CliRunner()
    out_file = tmp_path / 'out.json'
    # 使用项目自带的 data/input.json 作为配置
    res = runner.invoke(cli_main, [
        '--input', 'data/input.json',
        '--force', '100', '0', '0',
        '--moment', '0', '0', '0',
        '--output', str(out_file)
    ])
    assert res.exit_code == 0
    assert out_file.exists()
    data = json.loads(out_file.read_text(encoding='utf-8'))
    assert 'result' in data
    assert 'force_transformed' in data['result']
