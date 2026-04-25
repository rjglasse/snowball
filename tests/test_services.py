"""Tests for reusable project lifecycle services."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from snowball.models import Paper, PaperSource
from snowball.services import (
    ProjectContext,
    add_seed_dois,
    add_seed_pdfs,
    build_engine,
    create_project,
    load_project,
    parse_project_pdfs,
    run_snowball_iteration_checked,
)
from snowball.parsers.pdf_parser import PDFParseResult
from snowball.storage.json_storage import JSONStorage


class TestProjectServices:
    """Tests for project creation and loading services."""

    def test_create_project(self, tmp_path):
        """Project creation writes project metadata and pdfs directory."""
        project_dir = tmp_path / "slr"

        context = create_project(
            project_dir,
            name="Test SLR",
            description="Description",
            min_year=2020,
            max_year=2024,
            research_question="RQ?",
        )

        assert context.project_dir == project_dir
        assert (project_dir / "project.json").exists()
        assert (project_dir / "pdfs").exists()
        assert context.project.name == "Test SLR"
        assert context.project.filter_criteria.min_year == 2020
        assert context.project.filter_criteria.max_year == 2024
        context.storage.shutdown()

    def test_create_project_rejects_non_empty_directory(self, tmp_path):
        """Project creation rejects an existing non-empty directory."""
        (tmp_path / "file.txt").write_text("content")

        with pytest.raises(ValueError):
            create_project(tmp_path)

    def test_load_project(self, tmp_path):
        """Project loading returns storage, project, and engine components."""
        created = create_project(tmp_path / "slr", name="Loaded")
        created.storage.shutdown()

        loaded = load_project(tmp_path / "slr")

        assert loaded.project.name == "Loaded"
        assert loaded.engine is not None
        loaded.storage.shutdown()

    @patch("snowball.services.PDFParser")
    @patch("snowball.services.APIAggregator")
    def test_build_engine_uses_extraction_method(self, mock_api, mock_parser, tmp_path):
        """Engine construction passes through the requested extraction method."""
        storage = JSONStorage(tmp_path)

        build_engine(storage, extraction_method="grobid")

        mock_parser.assert_called_once_with(extraction_method="grobid")
        storage.shutdown()


class TestSeedServices:
    """Tests for seed import services."""

    def test_add_seed_pdfs_copies_pdf_and_saves_path(self, tmp_path):
        """PDF seed import delegates to the engine and copies the PDF."""
        context = create_project(tmp_path / "slr", name="PDF Seeds")
        pdf_path = tmp_path / "seed.pdf"
        pdf_path.write_bytes(b"%PDF")

        paper = Paper(id="paper-1", title="Seed Paper", source=PaperSource.SEED)
        context.engine = Mock()
        context.engine.add_seed_from_pdf.return_value = paper

        result = add_seed_pdfs(context, [pdf_path])

        assert len(result.added) == 1
        assert result.skipped == []
        assert (context.project_dir / "pdfs" / "paper-1.pdf").exists()
        saved = context.storage.load_paper("paper-1")
        assert saved.pdf_path.endswith("paper-1.pdf")
        context.storage.shutdown()

    def test_add_seed_pdfs_skips_missing_pdf(self, tmp_path):
        """PDF seed import reports missing files."""
        context = create_project(tmp_path / "slr", name="PDF Seeds")

        result = add_seed_pdfs(context, [tmp_path / "missing.pdf"])

        assert result.added == []
        assert "PDF not found" in result.skipped[0]
        context.storage.shutdown()

    def test_add_seed_pdfs_stages_failed_pdf_in_inbox(self, tmp_path):
        """PDF seed import keeps failed seed PDFs available for later parsing."""
        context = create_project(tmp_path / "slr", name="PDF Seeds")
        pdf_path = tmp_path / "seed.pdf"
        pdf_path.write_bytes(b"%PDF")
        context.engine = Mock()
        context.engine.add_seed_from_pdf.return_value = None

        result = add_seed_pdfs(context, [pdf_path])

        assert result.added == []
        assert (context.project_dir / "pdfs" / "inbox" / "seed.pdf").exists()
        assert any("Copied PDF to inbox" in item for item in result.skipped)
        context.storage.shutdown()

    def test_add_seed_dois(self, tmp_path):
        """DOI seed import delegates to the engine."""
        context = create_project(tmp_path / "slr", name="DOI Seeds")
        paper = Paper(id="paper-1", title="DOI Paper", source=PaperSource.SEED)
        context.engine = Mock()
        context.engine.add_seed_from_doi.return_value = paper

        result = add_seed_dois(context, ["10.1234/test"])

        assert result.added == [paper]
        assert result.skipped == []
        context.engine.add_seed_from_doi.assert_called_once_with("10.1234/test", context.project)
        context.storage.shutdown()


class TestWorkflowServices:
    """Tests for shared CLI/TUI workflow services."""

    def test_run_snowball_iteration_checked_blocks_pending_papers(self, tmp_path):
        """Guarded snowballing reports the engine's block reason."""
        context = create_project(tmp_path / "slr", name="Guarded")
        context.engine = Mock()
        context.engine.can_start_iteration.return_value = (False, "pending papers need review")

        result = run_snowball_iteration_checked(context)

        assert not result.can_start
        assert result.blocked_reason == "pending papers need review"
        context.engine.run_snowball_iteration.assert_not_called()
        context.storage.shutdown()

    def test_run_snowball_iteration_checked_runs_when_allowed(self, tmp_path):
        """Guarded snowballing delegates to the engine when allowed."""
        context = create_project(tmp_path / "slr", name="Guarded")
        context.engine = Mock()
        context.engine.can_start_iteration.return_value = (True, "")
        context.engine.run_snowball_iteration.return_value = {"added": 1}

        result = run_snowball_iteration_checked(context, direction="backward")

        assert result.can_start
        assert result.stats == {"added": 1}
        context.engine.run_snowball_iteration.assert_called_once_with(
            context.project,
            direction="backward",
        )
        context.storage.shutdown()

    @patch("snowball.services.PDFParser")
    def test_parse_project_pdfs_uses_extraction_method_and_moves_inbox_pdf(
        self,
        mock_parser_cls,
        tmp_path,
    ):
        """Project PDF parsing honors extraction mode and stages matched inbox PDFs."""
        context = create_project(tmp_path / "slr", name="PDF Parse")
        mock_parser_cls.reset_mock()
        paper = Paper(id="paper-1", title="A Matched Study", source=PaperSource.SEED)
        context.storage.save_paper(paper)

        inbox_dir = context.project_dir / "pdfs" / "inbox"
        inbox_dir.mkdir(parents=True)
        pdf_path = inbox_dir / "study.pdf"
        pdf_path.write_bytes(b"%PDF")

        parse_result = PDFParseResult()
        parse_result.title = "A Matched Study"
        parse_result.references = [{"title": "Reference One"}]
        mock_parser = mock_parser_cls.return_value
        mock_parser.parse.return_value = parse_result

        result = parse_project_pdfs(context, extraction_method="grobid")

        assert result.processed == 1
        assert result.no_match == 0
        mock_parser_cls.assert_called_once_with(extraction_method="grobid")
        assert not pdf_path.exists()
        moved_path = context.project_dir / "pdfs" / "study.pdf"
        assert moved_path.exists()

        saved = context.storage.load_paper("paper-1")
        assert saved.pdf_path == str(moved_path)
        assert saved.raw_data["grobid_references"] == [{"title": "Reference One"}]
        context.storage.shutdown()
