import pytest

from gui.signal_bus import SignalBus


class DummyPanel:
    def __init__(self):
        from src.models.project_model import CoordinateSystem, ReferenceValues
        self._cs = CoordinateSystem()
        self._refs = ReferenceValues()

    def get_coordinate_system_model(self):
        return self._cs

    def get_reference_values_model(self):
        return self._refs


class DummyGUI:
    def __init__(self):
        self.signal_bus = SignalBus.instance()
        self.source_panel = DummyPanel()
        self.target_panel = DummyPanel()
        # minimal text fields
        class Txt:
            def __init__(self, t=''):
                self._t = t

            def text(self):
                return self._t

        self.src_part_name = Txt('')
        self.tgt_part_name = Txt('')


def test_add_and_remove_source_part_emits_signals(monkeypatch):
    # Prevent QMessageBox dialogs from blocking tests
    import gui.part_manager as pm

    monkeypatch.setattr(pm, 'QMessageBox', type('M', (), {'information': lambda *a, **k: None, 'warning': lambda *a, **k: None, 'critical': lambda *a, **k: None}))

    gui = DummyGUI()
    bus = gui.signal_bus

    events = {'added': None, 'removed': None}

    def on_added(side, name):
        events['added'] = (side, name)

    def on_removed(side, name):
        events['removed'] = (side, name)

    bus.partAdded.connect(on_added)
    bus.partRemoved.connect(on_removed)

    mgr = pm.PartManager(gui)

    # Add source part
    mgr.add_source_part(suggested_name='TestPart')
    assert 'TestPart' in gui.project_model.source_parts
    assert events['added'] == ('Source', 'TestPart')

    # Remove source part
    mgr.remove_source_part(name_hint='TestPart')
    assert 'TestPart' not in gui.project_model.source_parts
    assert events['removed'] == ('Source', 'TestPart')
