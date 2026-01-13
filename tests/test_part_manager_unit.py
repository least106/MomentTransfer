from src.models.project_model import (
    ProjectConfigModel,
    Part,
    PartVariant,
    CoordinateSystem,
    ReferenceValues,
)
from gui.part_manager import PartManager


class DummySelector:
    def __init__(self, text=""):
        self._text = text

    def currentText(self):
        return self._text


class DummyLineEdit:
    def __init__(self, text=""):
        self._text = text

    def text(self):
        return self._text


class DummyPanel:
    def __init__(self, name="P"):
        self.part_selector = DummySelector(name)
        self._applied = None

    def get_coordinate_system_model(self):
        return CoordinateSystem()

    def get_reference_values_model(self):
        return ReferenceValues()

    def apply_variant_payload(self, payload):
        self._applied = payload

    def to_variant_payload(self, part_name):
        return {"PartName": part_name}


class DummyGUI:
    def __init__(self):
        self.project_model = None
        self.source_panel = DummyPanel("P")
        self.src_part_name = DummyLineEdit("P")
        # minimal attributes used by PartManager


def test_save_current_source_part_creates_model_entry():
    gui = DummyGUI()
    pm = PartManager(gui)
    # ensure project model created and source part saved
    pm.save_current_source_part()
    assert gui.project_model is not None
    assert "P" in gui.project_model.source_parts


def test_on_source_part_changed_applies_payload():
    gui = DummyGUI()
    gui.project_model = ProjectConfigModel()
    # prepare a Part with one variant
    pv = PartVariant(
        part_name="P", coord_system=CoordinateSystem(), refs=ReferenceValues()
    )
    gui.project_model.source_parts["P"] = Part(part_name="P", variants=[pv])
    # source panel selector already returns 'P'
    pm = PartManager(gui)
    pm.on_source_part_changed()
    assert gui.source_panel._applied is not None
    assert gui._current_source_part_name == "P"
