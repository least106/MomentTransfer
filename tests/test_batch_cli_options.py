from click.testing import CliRunner

import batch


def test_batch_help_shows_enable_sidecar_and_hides_registry_db():
    runner = CliRunner()
    res = runner.invoke(batch.main, ["--help"])
    assert res.exit_code == 0
    out = res.output
    assert "--enable-sidecar" in out
    # registry-db is hidden; it should not appear in help
    assert "--registry-db" not in out
