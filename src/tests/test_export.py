"""Tests for export functionality."""
import zipfile
from pathlib import Path
from promptsmith.scripts.export import export_promptsmith


def test_export_creates_zip(tmp_path):
    """Test that export creates a zip file."""
    # Create test directories
    (tmp_path / "profiles").mkdir()
    (tmp_path / "templates").mkdir()
    (tmp_path / "config.yaml").write_text("default_profile: test")
    
    # Create a test profile
    (tmp_path / "profiles" / "test.yaml").write_text("name: Test\nrole: Tester\n")
    
    # Export
    export_path = export_promptsmith(root=tmp_path, output_dir=tmp_path / "exports")
    
    assert export_path.exists()
    assert export_path.suffix == ".zip"
    assert "PromptSmith-cli-Export" in export_path.name


def test_export_contains_files(tmp_path):
    """Test that export zip contains the expected files."""
    # Create test directories
    (tmp_path / "profiles").mkdir()
    (tmp_path / "templates").mkdir()
    (tmp_path / "config.yaml").write_text("default_profile: test")
    
    # Create test files
    (tmp_path / "profiles" / "test.yaml").write_text("name: Test\nrole: Tester\n")
    (tmp_path / "templates" / "test.yaml").write_text("name: Test\nprompt: Hello\n")
    
    # Export
    export_path = export_promptsmith(root=tmp_path, output_dir=tmp_path / "exports")
    
    # Check contents
    with zipfile.ZipFile(export_path, "r") as zf:
        files = zf.namelist()
        assert any("profiles/test.yaml" in f for f in files)
        assert any("templates/test.yaml" in f for f in files)
        assert any("config.yaml" in f for f in files)


class TestExportSourceCode:
    """Regression tests for a real bug: the old 'Export Full Application'
    button called the same export_promptsmith() function used elsewhere,
    which only ever bundles profiles/templates/config.yaml - never the
    actual source code. Confirmed directly by inspecting a real exported
    zip: zero .py files, no pyproject.toml, no README. Renamed to
    export_source_code() for clarity, since it exports the project's
    source for someone to build themselves - it does not include a Python
    runtime or a working executable, which an external review correctly
    pointed out was a confusing thing for "Export Full Application" to
    imply."""

    def _make_fake_project(self, tmp_path):
        (tmp_path / "src" / "promptsmith" / "core").mkdir(parents=True)
        (tmp_path / "src" / "promptsmith" / "core" / "refiner.py").write_text("# refiner code")
        (tmp_path / "src" / "promptsmith" / "__init__.py").write_text("")
        (tmp_path / "profiles").mkdir()
        (tmp_path / "profiles" / "test.yaml").write_text("name: Test\nrole: Tester\n")
        (tmp_path / "templates").mkdir()
        (tmp_path / "templates" / "test.yaml").write_text("name: Test\nprompt: Hello\n")
        (tmp_path / "pyproject.toml").write_text("[project]\nname = \"promptsmith\"\n")
        (tmp_path / "README.md").write_text("# PromptSmith")
        (tmp_path / "config.yaml").write_text("default_profile: test")
        # Things that must be excluded even though they're plausible dirs.
        (tmp_path / ".venv" / "lib").mkdir(parents=True)
        (tmp_path / ".venv" / "lib" / "somepkg.py").write_text("# should not be included")
        (tmp_path / "src" / "promptsmith" / "__pycache__").mkdir()
        (tmp_path / "src" / "promptsmith" / "__pycache__" / "refiner.cpython-312.pyc").write_bytes(b"\x00")
        (tmp_path / "models").mkdir()
        (tmp_path / "models" / "fake-model.gguf").write_bytes(b"\x00" * 100)

    def test_includes_source_code(self, tmp_path):
        from promptsmith.scripts.export import export_source_code
        self._make_fake_project(tmp_path)
        export_path = export_source_code(root=tmp_path, output_dir=tmp_path / "exports")
        with zipfile.ZipFile(export_path) as zf:
            names = zf.namelist()
            assert any(n.endswith(".py") for n in names), "Full application export must include source code"
            assert "pyproject.toml" in names
            assert "README.md" in names

    def test_includes_profiles_and_templates(self, tmp_path):
        from promptsmith.scripts.export import export_source_code
        self._make_fake_project(tmp_path)
        export_path = export_source_code(root=tmp_path, output_dir=tmp_path / "exports")
        with zipfile.ZipFile(export_path) as zf:
            names = zf.namelist()
            assert any("profiles/test.yaml" in n for n in names)
            assert any("templates/test.yaml" in n for n in names)

    def test_excludes_venv_pycache_and_models(self, tmp_path):
        from promptsmith.scripts.export import export_source_code
        self._make_fake_project(tmp_path)
        export_path = export_source_code(root=tmp_path, output_dir=tmp_path / "exports")
        with zipfile.ZipFile(export_path) as zf:
            names = zf.namelist()
            assert not any(".venv" in n for n in names)
            assert not any("__pycache__" in n or n.endswith(".pyc") for n in names)
            assert not any(n.startswith("models/") or n.endswith(".gguf") for n in names)

    def test_filename_distinguishes_from_data_only_export(self, tmp_path):
        """The source-code export must use a visibly different filename
        than export_promptsmith()'s output, so the two are never mistaken
        for each other again."""
        from promptsmith.scripts.export import export_source_code
        self._make_fake_project(tmp_path)
        export_path = export_source_code(root=tmp_path, output_dir=tmp_path / "exports")
        assert "SourceCode" in export_path.name
