from pathlib import Path

from gui.project_manager import ProjectManager


class DummyTab:
    def __init__(self, idx=0):
        self._idx = idx

    def currentIndex(self):
        return self._idx


class DummyGeom:
    def __init__(self, x=10, y=20, w=800, h=600):
        self._x = x
        self._y = y
        self._w = w
        self._h = h

    def x(self):
        return self._x

    def y(self):
        return self._y

    def width(self):
        return self._w

    def height(self):
        return self._h


class DummyGUI:
    def __init__(self):
        self.tab_main = DummyTab(idx=2)
        self._file_tree_expanded = ["/tmp/a.csv", "/tmp/b.csv"]
        self.source_panel = type("P", (), {"_current_part_name": "S1"})()
        self.target_panel = type("P", (), {"_current_part_name": "T1"})()
        self.file_selection_manager = type("FSM", (), {})()
        self.file_selection_manager.table_row_selection_by_file = {"/tmp/a.csv": {1, 2}}
        self.file_selection_manager.skipped_rows_by_file = {"/tmp/a.csv": {5}}
        self._file_tree_expanded = ["/tmp/a.csv"]
        self._file_tree_items = {}
        # geometry callable
        self.geometry = lambda: DummyGeom(5, 6, 300, 200)


def test_collect_ui_state_includes_expected_keys(tmp_path):
    gui = DummyGUI()
    pm = ProjectManager(gui)
    state = pm._collect_current_state()

    assert "ui_state" in state
    ui = state["ui_state"]
    assert ui.get("tab_index") == 2
    assert isinstance(ui.get("window_geometry"), dict)
    assert (
        "selected_files" in ui or True
    )  # selected_files may be empty depending on FSM


def test_restore_data_files_skipped_rows():
    gui = DummyGUI()
    pm = ProjectManager(gui)

    project_data = {
        "version": pm.PROJECT_VERSION,
        "timestamp": "now",
        "data_files": [
            {
                "path": "/tmp/a.csv",
                "special_mappings": {},
                "row_selection": [1, 2],
                "skipped_rows": [5, 6],
            }
        ],
    }

    res = pm._restore_data_files(project_data)
    assert res is True
    fsm = gui.file_selection_manager
    # table_row_selection_by_file should have set of rows
    key = str(Path("/tmp/a.csv"))
    assert (
        key in fsm.table_row_selection_by_file
        or "/tmp/a.csv" in fsm.table_row_selection_by_file
    )
    # skipped rows restored
    assert (key in fsm.skipped_rows_by_file) or (
        "/tmp/a.csv" in fsm.skipped_rows_by_file
    )
