import pytest
from pathlib import Path
from promptsmith.core.templates import TemplateManager
from promptsmith.core.exceptions import TemplateNotFoundError
import yaml


@pytest.fixture
def template_manager(tmp_path):
    tdir = tmp_path / "templates"
    tdir.mkdir()
    tmpl = {
        "name": "Test Template",
        "description": "A test template",
        "prompt": "Test prompt for {variable}",
        "version": 1,
    }
    (tdir / "test-template.yaml").write_text(yaml.dump(tmpl))
    return TemplateManager(tdir)


def test_load_templates(template_manager):
    assert "test-template" in template_manager.list_templates()


def test_get_template(template_manager):
    t = template_manager.get_template("test-template")
    assert t["description"] == "A test template"
    assert "{variable}" in t["prompt"]


def test_missing_template_raises(template_manager):
    with pytest.raises(TemplateNotFoundError):
        template_manager.get_template("ghost")


def test_add_template(template_manager):
    template_manager.add_template("new-tmpl", {"prompt": "hello {x}"})
    assert "new-tmpl" in template_manager.list_templates()
