"""Smoke tests for TUI module boundaries."""

from snowball.models import ReviewProject
from snowball.snowballing import SnowballEngine
from snowball.storage.json_storage import JSONStorage
from snowball.tui.app import SnowballApp, run_lifecycle_tui, run_tui
from snowball.tui.dialogs import (
    MetadataMismatchDialog,
    PDFChooserDialog,
    RelevanceMethodDialog,
    ReviewDialog,
)
from snowball.tui.setup import ProjectSetupApp


def test_tui_entry_points_importable():
    """Public TUI entry points remain importable after module split."""
    assert callable(run_tui)
    assert callable(run_lifecycle_tui)


def test_tui_dialogs_importable(sample_paper):
    """Dialog classes can be constructed without importing the main app."""
    assert ReviewDialog(sample_paper)
    assert MetadataMismatchDialog([("Title", "Current", "API")])
    assert PDFChooserDialog([])
    assert RelevanceMethodDialog()


def test_setup_app_constructs(tmp_path):
    """The setup app remains independently constructable."""
    app = ProjectSetupApp(initial_directory=tmp_path)

    assert app.initial_directory == tmp_path


def test_snowball_app_keeps_extraction_method(tmp_path):
    """The review app stores the extraction mode passed by lifecycle setup."""
    storage = JSONStorage(tmp_path)
    project = ReviewProject(name="TUI")
    storage.save_project(project)
    engine = SnowballEngine(storage, api_aggregator=None)

    app = SnowballApp(tmp_path, storage, engine, project, extraction_method="grobid")

    assert app.extraction_method == "grobid"
    storage.shutdown()


def test_snowball_app_stats_show_extraction_mode(tmp_path):
    """The review header exposes the active PDF extraction mode."""
    storage = JSONStorage(tmp_path)
    project = ReviewProject(name="TUI")
    storage.save_project(project)
    engine = SnowballEngine(storage, api_aggregator=None)
    app = SnowballApp(tmp_path, storage, engine, project, extraction_method="llm")

    assert "Extract:" in app._get_stats_text()
    assert "LLM" in app._get_stats_text()
    storage.shutdown()
