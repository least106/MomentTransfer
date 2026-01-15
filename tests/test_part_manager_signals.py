from gui.signal_bus import SignalBus


class DummyPanel:
    def __init__(self):
        from src.models.project_model import CoordinateSystem, ReferenceValues

        self._cs = CoordinateSystem()
        self._refs = ReferenceValues()
        
        # 添加必需的 part_name_input 和 part_selector 属性
        class DummyLineEdit:
            def __init__(self, t=""):
                self._t = t
            def text(self):
                return self._t
                
        self.part_name_input = DummyLineEdit("")
        self.part_selector = None  # 可选
        self._current_part_name = None

    def get_coordinate_system_model(self):
        return self._cs

    def get_reference_values_model(self):
        return self._refs


class DummyGUI:
    def __init__(self):
        self.signal_bus = SignalBus.instance()
        self.source_panel = DummyPanel()
        self.target_panel = DummyPanel()
        # 不再需要单独的 src_part_name 和 tgt_part_name，已在 Panel 中


def test_add_and_remove_source_part_emits_signals(monkeypatch):
    # Prevent QMessageBox dialogs from blocking tests
    import gui.part_manager as pm

    monkeypatch.setattr(
        pm,
        "QMessageBox",
        type(
            "M",
            (),
            {
                "information": lambda *a, **k: None,
                "warning": lambda *a, **k: None,
                "critical": lambda *a, **k: None,
            },
        ),
    )

    gui = DummyGUI()
    bus = gui.signal_bus

    events = {"added": None, "removed": None}

    def on_added(side, name):
        events["added"] = (side, name)

    def on_removed(side, name):
        events["removed"] = (side, name)

    bus.partAdded.connect(on_added)
    bus.partRemoved.connect(on_removed)

    mgr = pm.PartManager(gui)

    # Add source part
    mgr.add_source_part(suggested_name="TestPart")
    assert "TestPart" in gui.project_model.source_parts
    assert events["added"] == ("Source", "TestPart")

    # Remove source part
    mgr.remove_source_part(name_hint="TestPart")
    assert "TestPart" not in gui.project_model.source_parts
    assert events["removed"] == ("Source", "TestPart")
