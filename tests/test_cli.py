"""Tests for CLI functionality."""

import pytest
from unittest.mock import Mock, patch
import sys
import tempfile
from pathlib import Path
from typer.testing import CliRunner

from snowball.cli import main, init, add_seed, snowball, export, app


# Create a CLI runner for testing
runner = CliRunner()


class TestCLIHelpers:
    """Tests for CLI helper functions."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)

    def test_init_project_creates_directory(self, temp_dir):
        """Test that init command creates the project directory."""
        project_dir = temp_dir / "new_project"

        # Call the function directly with parameters
        init(
            directory=str(project_dir),
            name="Test Project",
            description="Test description",
            min_year=2020,
            max_year=2024,
            research_question=None,
        )

        assert project_dir.exists()
        assert (project_dir / "project.json").exists()

    def test_init_project_with_existing_directory(self, temp_dir):
        """Test init command fails with existing non-empty directory."""
        # Create a file in the directory to make it non-empty
        (temp_dir / "existing_file.txt").write_text("content")

        # Expect typer.Exit instead of SystemExit
        from typer import Exit

        with pytest.raises(Exit):
            init(
                directory=str(temp_dir),
                name="Test",
                description="",
                min_year=None,
                max_year=None,
                research_question=None,
            )

    def test_init_project_uses_defaults(self, temp_dir):
        """Test init command uses defaults for optional parameters."""
        project_dir = temp_dir / "project"

        init(
            directory=str(project_dir),
            name=None,  # Should use directory name
            description=None,
            min_year=None,
            max_year=None,
            research_question=None,
        )

        from snowball.storage.json_storage import JSONStorage

        storage = JSONStorage(project_dir)
        project = storage.load_project()

        assert project.name == "project"  # Directory name


class TestCLIAddSeed:
    """Tests for add-seed command."""

    @pytest.fixture
    def initialized_project(self, temp_project_dir, sample_project):
        """Create an initialized project directory."""
        from snowball.storage.json_storage import JSONStorage

        storage = JSONStorage(temp_project_dir)
        storage.save_project(sample_project)
        return temp_project_dir

    @patch("snowball.cli.APIAggregator")
    @patch("snowball.cli.SnowballEngine")
    def test_add_seed_by_doi(
        self, mock_engine_class, mock_api_class, initialized_project
    ):
        """Test adding seed by DOI."""
        mock_engine = Mock()
        mock_engine.add_seed_from_doi.return_value = Mock(title="Found Paper")
        mock_engine_class.return_value = mock_engine
        mock_api_class.return_value = Mock()

        add_seed(
            directory=str(initialized_project),
            pdf=None,
            doi=["10.1234/test"],
            s2_api_key=None,
            email=None,
            no_grobid=True,
            use_scholar=False,
            scholar_proxy=None,
            scholar_free_proxy=False,
        )

        mock_engine.add_seed_from_doi.assert_called_once()

    def test_add_seed_no_project(self, temp_project_dir):
        """Test add_seed fails when no project exists."""
        from typer import Exit

        with pytest.raises(Exit):
            add_seed(
                directory=str(temp_project_dir),
                pdf=None,
                doi=["10.1234/test"],
                s2_api_key=None,
                email=None,
                no_grobid=False,
                use_scholar=False,
                scholar_proxy=None,
                scholar_free_proxy=False,
            )


class TestCLISnowball:
    """Tests for snowball command."""

    @pytest.fixture
    def project_with_seeds(self, temp_project_dir, sample_project, sample_paper):
        """Create a project with seed papers."""
        from snowball.storage.json_storage import JSONStorage

        storage = JSONStorage(temp_project_dir)

        sample_project.seed_paper_ids = [sample_paper.id]
        storage.save_project(sample_project)
        storage.save_paper(sample_paper)

        return temp_project_dir

    @patch("snowball.cli.APIAggregator")
    @patch("snowball.cli.SnowballEngine")
    def test_run_snowball_iteration(
        self, mock_engine_class, mock_api_class, project_with_seeds
    ):
        """Test running snowball iterations."""
        mock_engine = Mock()
        mock_engine.should_continue_snowballing.side_effect = [True, False]
        mock_engine.can_start_iteration.return_value = (True, "")
        mock_engine.run_snowball_iteration.return_value = {
            "added": 10,
            "backward": 5,
            "forward": 5,
            "auto_excluded": 2,
            "for_review": 8,
        }
        mock_engine_class.return_value = mock_engine
        mock_api_class.return_value = Mock()

        from snowball.cli import SnowballDirection

        snowball(
            directory=str(project_with_seeds),
            iterations=1,
            direction=SnowballDirection.both,
            s2_api_key=None,
            email=None,
            force=False,
            use_scholar=False,
            scholar_proxy=None,
            scholar_free_proxy=False,
        )

        mock_engine.run_snowball_iteration.assert_called()


class TestCLIExport:
    """Tests for export command."""

    @pytest.fixture
    def project_with_papers(self, temp_project_dir, sample_project, sample_papers):
        """Create a project with papers to export."""
        from snowball.storage.json_storage import JSONStorage

        storage = JSONStorage(temp_project_dir)
        storage.save_project(sample_project)
        for paper in sample_papers:
            storage.save_paper(paper)
        return temp_project_dir

    def test_export_bibtex(self, project_with_papers):
        """Test exporting BibTeX."""
        from snowball.cli import ExportFormat

        export(
            directory=str(project_with_papers),
            format=ExportFormat.bibtex,
            output=None,
            included_only=False,
            standalone=False,
        )

        # Check that BibTeX file was created in output/ folder
        bib_file = project_with_papers / "output" / "all_papers.bib"
        assert bib_file.exists()

    def test_export_csv(self, project_with_papers):
        """Test exporting CSV."""
        from snowball.cli import ExportFormat

        export(
            directory=str(project_with_papers),
            format=ExportFormat.csv,
            output=None,
            included_only=False,
            standalone=False,
        )

        # Check that CSV file was created in output/ folder
        csv_file = project_with_papers / "output" / "all_papers.csv"
        assert csv_file.exists()

    def test_export_all_formats(self, project_with_papers):
        """Test exporting all formats."""
        from snowball.cli import ExportFormat

        export(
            directory=str(project_with_papers),
            format=ExportFormat.all,
            output=None,
            included_only=False,
            standalone=False,
        )

        # Files are now in output/ folder
        assert (project_with_papers / "output" / "all_papers.bib").exists()
        assert (project_with_papers / "output" / "all_papers.csv").exists()

    def test_export_included_only(self, project_with_papers):
        """Test exporting only included papers."""
        from snowball.cli import ExportFormat

        export(
            directory=str(project_with_papers),
            format=ExportFormat.bibtex,
            output=None,
            included_only=True,
            standalone=False,
        )

        # Files are now in output/ folder
        bib_file = project_with_papers / "output" / "included_papers.bib"
        assert bib_file.exists()


class TestCLIMain:
    """Tests for main CLI entry point."""

    def test_main_no_command(self):
        """Test main with no command shows help or returns usage error."""
        result = runner.invoke(app, [])
        # Typer returns 2 for missing required command (which is correct behavior for usage errors)
        # The help text should be shown
        assert result.exit_code == 2
        assert "Usage:" in result.stdout

    def test_main_init_command(self):
        """Test main dispatches to init command."""
        with tempfile.TemporaryDirectory() as temp_dir:
            result = runner.invoke(app, ["init", temp_dir, "--name", "Test"])
            # Should succeed
            assert result.exit_code == 0
            assert Path(temp_dir, "project.json").exists()

    @patch("snowball.cli.APIAggregator")
    @patch("snowball.cli.SnowballEngine")
    def test_main_add_seed_command(self, mock_engine_class, mock_api_class):
        """Test main dispatches to add_seed command."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # First init a project
            runner.invoke(app, ["init", temp_dir])

            # Mock the engine
            mock_engine = Mock()
            mock_engine.add_seed_from_doi.return_value = Mock(title="Test Paper")
            mock_engine_class.return_value = mock_engine
            mock_api_class.return_value = Mock()

            # Then add a seed
            result = runner.invoke(
                app, ["add-seed", temp_dir, "--doi", "10.1234/test"]
            )
            # Should succeed (or at least try)
            assert result.exit_code == 0
