"""Tests for path utilities."""
from pathlib import Path
from promptsmith.utils.path_utils import get_project_root, get_asset_path


def test_get_project_root():
    """Test that get_project_root finds the project root."""
    root = get_project_root(__file__)
    
    # The project root should contain pyproject.toml
    assert (root / "pyproject.toml").exists()
    assert root.is_absolute()


def test_get_asset_path_profiles():
    """Test that get_asset_path returns correct path for profiles."""
    profiles_path = get_asset_path("profiles", __file__)
    
    assert profiles_path.is_absolute()
    assert profiles_path.name == "profiles"


def test_get_asset_path_templates():
    """Test that get_asset_path returns correct path for templates."""
    templates_path = get_asset_path("templates", __file__)
    
    assert templates_path.is_absolute()
    assert templates_path.name == "templates"


def test_get_asset_path_models():
    """Test that get_asset_path returns correct path for models."""
    models_path = get_asset_path("models", __file__)
    
    assert models_path.is_absolute()
    assert models_path.name == "models"


class TestFrozenModeResolution:
    """Regression tests for the fundamental bug that blocked building
    standalone macOS/Windows executables: get_project_root() walked up
    looking for pyproject.toml, a build-time file never shipped inside a
    PyInstaller bundle. Worse, it ran at module import time in app.py, so
    a built executable couldn't even get past import - it crashed before
    the UI ever started. Fixed by detecting PyInstaller's frozen runtime
    and resolving against sys.executable's directory - deliberately NOT
    sys._MEIPASS, which in a --onedir build points at the hidden
    _internal/ runtime folder, not the top-level directory where
    profiles/templates/models are meant to live as visible, directly
    editable folders alongside the executable."""

    def test_is_frozen_false_in_normal_execution(self):
        from promptsmith.utils.path_utils import is_frozen
        assert is_frozen() is False

    def test_is_frozen_true_when_pyinstaller_attributes_present(self, monkeypatch):
        import sys
        from promptsmith.utils.path_utils import is_frozen
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", "/fake/bundle", raising=False)
        assert is_frozen() is True

    def test_project_root_uses_executable_directory_when_frozen(self, monkeypatch, tmp_path):
        """The key behavior: root must be the executable's own directory
        (the visible top-level folder), not sys._MEIPASS (the hidden
        _internal/ folder) - confirmed these differ in a real PyInstaller
        6.x onedir build (sys._MEIPASS == <top-level>/_internal)."""
        import sys
        fake_exe = tmp_path / "_internal_subdir" / "PromptSmith"
        fake_exe.parent.mkdir(parents=True)
        fake_exe.touch()
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "some_other_meipass_dir"), raising=False)
        monkeypatch.setattr(sys, "executable", str(fake_exe), raising=False)
        root = get_project_root()
        assert root == fake_exe.parent
        assert root != Path(tmp_path / "some_other_meipass_dir")

    def test_project_root_ignores_missing_pyproject_when_frozen(self, monkeypatch, tmp_path):
        """The whole point of the fix: no pyproject.toml exists in a
        frozen bundle, and that must not raise."""
        import sys
        fake_exe = tmp_path / "PromptSmith"
        fake_exe.touch()
        assert not (tmp_path / "pyproject.toml").exists()
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
        monkeypatch.setattr(sys, "executable", str(fake_exe), raising=False)
        root = get_project_root()
        assert root == tmp_path

    def test_asset_path_resolves_next_to_executable_when_frozen(self, monkeypatch, tmp_path):
        import sys
        fake_exe = tmp_path / "PromptSmith"
        fake_exe.touch()
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "_internal"), raising=False)
        monkeypatch.setattr(sys, "executable", str(fake_exe), raising=False)
        models_path = get_asset_path("models")
        assert models_path == tmp_path / "models"

    def test_normal_mode_unaffected_by_frozen_check(self):
        """Sanity check: adding the frozen check must not change behavior
        for a normal, non-frozen run."""
        root = get_project_root(__file__)
        assert (root / "pyproject.toml").exists()


class TestUserDataDirResolution:
    """Regression tests for the bug where saved profile/template edits and
    the log file were invisible next to a distributed executable: unlike
    get_project_root()/get_asset_path(), get_user_data_dir() ignored
    is_frozen() entirely and always wrote to the OS home directory
    (~/.promptsmith), even in a portable build that exposes profiles/,
    templates/, and models/ as siblings of the executable. A user editing
    and saving a profile in that build had no way to find where it went."""

    def test_user_data_dir_next_to_executable_when_frozen(self, monkeypatch, tmp_path):
        import sys
        from promptsmith.utils.path_utils import get_user_data_dir
        monkeypatch.delenv("PROMPTSMITH_LOG_DIR", raising=False)
        fake_exe = tmp_path / "PromptSmith"
        fake_exe.touch()
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "_internal"), raising=False)
        monkeypatch.setattr(sys, "executable", str(fake_exe), raising=False)

        result = get_user_data_dir()

        assert result == tmp_path / "user_data"
        assert result.parent == fake_exe.parent
        assert result.exists()  # mkdir(parents=True, exist_ok=True) side effect

    def test_user_data_dir_defaults_to_home_when_not_frozen(self, monkeypatch, tmp_path):
        from promptsmith.utils.path_utils import get_user_data_dir
        monkeypatch.delenv("PROMPTSMITH_LOG_DIR", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        result = get_user_data_dir()

        assert result == tmp_path / ".promptsmith"

    def test_user_data_dir_env_override_wins_regardless_of_frozen_state(self, monkeypatch, tmp_path):
        import sys
        from promptsmith.utils.path_utils import get_user_data_dir
        override = tmp_path / "explicit-override"
        monkeypatch.setenv("PROMPTSMITH_LOG_DIR", str(override))
        fake_exe = tmp_path / "PromptSmith"
        fake_exe.touch()
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "_internal"), raising=False)
        monkeypatch.setattr(sys, "executable", str(fake_exe), raising=False)

        result = get_user_data_dir()

        assert result == override
