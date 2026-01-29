from gui.batch_thread import BatchProcessThread


def test_process_special_format_branch(monkeypatch, tmp_path):
    # 准备环境
    p = tmp_path / "f.mtfmt"
    p.write_text("dummy", encoding="utf-8")

    thread = BatchProcessThread(None, [], tmp_path, {})
    # 新版实现将 project_data 存放在 config 中，测试适配为设置 config.project_data
    thread.config.project_data = object()

    # 强制 looks_like_special_format 返回 True
    monkeypatch.setattr("gui.batch_thread.looks_like_special_format", lambda fp: True)

    # 模拟 process_special_format_file 返回 outputs 和 report
    def fake_proc(fp, project_data, output_dir, **kwargs):
        return (
            [output_dir / "out1.csv"],
            [{"status": "success", "part": "P1", "out_path": "out1.csv"}],
        )

    monkeypatch.setattr("gui.batch_thread.process_special_format_file", fake_proc)

    # 捕获日志消息
    msgs = []

    class DS:
        def emit(self, m):
            msgs.append(m)

    thread.log_message = DS()

    res = thread._process_special_format_branch(p)
    assert isinstance(res, list)
    assert len(msgs) >= 1
