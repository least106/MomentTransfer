from click.testing import CliRunner

import batch


def test_batch_help_no_enable_sidecar():
    """验证 enable_sidecar 和 registry_db 选项已被移除"""
    runner = CliRunner()
    res = runner.invoke(batch.main, ["--help"])
    assert res.exit_code == 0
    out = res.output
    # 确保已移除的选项不出现
    assert "--enable-sidecar" not in out
    assert "--registry-db" not in out
