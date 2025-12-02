"""Tests for CLI functionality."""

import pytest
from unittest.mock import Mock, patch
import sys
import tempfile
from pathlib import Path

from snowball.cli import main, init_project, add_seed, run_snowball, export_results


class TestCLIHelpers:
    """Tests for CLI helper functions."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)

    def test_init_project_creates_directory(self, temp_dir):
        """Test that init_project creates the project directory."""
        project_dir = temp_dir / "new_project"
        
        args = Mock()
        args.directory = str(project_dir)
        args.name = "Test Project"
        args.description = "Test description"
        args.max_iterations = 2
        args.min_year = 2020
        args.max_year = 2024
        
        init_project(args)
        
        assert project_dir.exists()
        assert (project_dir / "project.json").exists()

    def test_init_project_with_existing_directory(self, temp_dir):
        """Test init_project fails with existing non-empty directory."""
        # Create a file in the directory to make it non-empty
        (temp_dir / "existing_file.txt").write_text("content")
        
        args = Mock()
        args.directory = str(temp_dir)
        args.name = "Test"
        args.description = ""
        args.max_iterations = 1
        args.min_year = None
        args.max_year = None
        
        with pytest.raises(SystemExit):
            init_project(args)

    def test_init_project_uses_defaults(self, temp_dir):
        """Test init_project uses defaults for optional parameters."""
        project_dir = temp_dir / "project"
        
        args = Mock()
        args.directory = str(project_dir)
        args.name = None  # Should use directory name
        args.description = None
        args.max_iterations = None
        args.min_year = None
        args.max_year = None
        
        init_project(args)
        
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

    @patch('snowball.cli.APIAggregator')
    @patch('snowball.cli.SnowballEngine')
    def test_add_seed_by_doi(self, mock_engine_class, mock_api_class, initialized_project):
        """Test adding seed by DOI."""
        mock_engine = Mock()
        mock_engine.add_seed_from_doi.return_value = Mock(title="Found Paper")
        mock_engine_class.return_value = mock_engine
        mock_api_class.return_value = Mock()
        
        args = Mock()
        args.directory = str(initialized_project)
        args.pdf = None
        args.doi = ["10.1234/test"]
        args.s2_api_key = None
        args.email = None
        args.no_grobid = True
        
        add_seed(args)
        
        mock_engine.add_seed_from_doi.assert_called_once_with("10.1234/test", mock_engine.add_seed_from_doi.call_args[0][1])

    def test_add_seed_no_project(self, temp_project_dir):
        """Test add_seed fails when no project exists."""
        args = Mock()
        args.directory = str(temp_project_dir)
        args.pdf = None
        args.doi = ["10.1234/test"]
        
        with pytest.raises(SystemExit):
            add_seed(args)


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

    @patch('snowball.cli.APIAggregator')
    @patch('snowball.cli.SnowballEngine')
    def test_run_snowball_iteration(self, mock_engine_class, mock_api_class, project_with_seeds):
        """Test running snowball iterations."""
        mock_engine = Mock()
        mock_engine.should_continue_snowballing.side_effect = [True, False]
        mock_engine.run_snowball_iteration.return_value = {
            "added": 10,
            "backward": 5,
            "forward": 5,
            "auto_excluded": 2,
            "for_review": 8
        }
        mock_engine_class.return_value = mock_engine
        mock_api_class.return_value = Mock()
        
        args = Mock()
        args.directory = str(project_with_seeds)
        args.iterations = 1
        args.s2_api_key = None
        args.email = None
        
        run_snowball(args)
        
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
        args = Mock()
        args.directory = str(project_with_papers)
        args.format = "bibtex"
        args.output = None
        args.included_only = False
        
        export_results(args)
        
        # Check that BibTeX file was created
        bib_file = project_with_papers / "all_papers.bib"
        assert bib_file.exists()

    def test_export_csv(self, project_with_papers):
        """Test exporting CSV."""
        args = Mock()
        args.directory = str(project_with_papers)
        args.format = "csv"
        args.output = None
        args.included_only = False
        
        export_results(args)
        
        # Check that CSV file was created
        csv_file = project_with_papers / "all_papers.csv"
        assert csv_file.exists()

    def test_export_all_formats(self, project_with_papers):
        """Test exporting all formats."""
        args = Mock()
        args.directory = str(project_with_papers)
        args.format = "all"
        args.output = None
        args.included_only = False
        
        export_results(args)
        
        assert (project_with_papers / "all_papers.bib").exists()
        assert (project_with_papers / "all_papers.csv").exists()

    def test_export_included_only(self, project_with_papers):
        """Test exporting only included papers."""
        args = Mock()
        args.directory = str(project_with_papers)
        args.format = "bibtex"
        args.output = None
        args.included_only = True
        
        export_results(args)
        
        bib_file = project_with_papers / "included_papers.bib"
        assert bib_file.exists()


class TestCLIMain:
    """Tests for main CLI entry point."""

    def test_main_no_command(self):
        """Test main with no command shows help."""
        with patch.object(sys, 'argv', ['snowball']):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    @patch('snowball.cli.init_project')
    def test_main_init_command(self, mock_init):
        """Test main dispatches to init_project."""
        with patch.object(sys, 'argv', ['snowball', 'init', '/tmp/test']):
            main()
        mock_init.assert_called_once()

    @patch('snowball.cli.add_seed')
    def test_main_add_seed_command(self, mock_add_seed):
        """Test main dispatches to add_seed."""
        with patch.object(sys, 'argv', ['snowball', 'add-seed', '/tmp/test', '--doi', '10.1234/test']):
            main()
        mock_add_seed.assert_called_once()

    @patch('snowball.cli.run_snowball')
    def test_main_snowball_command(self, mock_snowball):
        """Test main dispatches to run_snowball."""
        with patch.object(sys, 'argv', ['snowball', 'snowball', '/tmp/test']):
            main()
        mock_snowball.assert_called_once()

    @patch('snowball.cli.export_results')
    def test_main_export_command(self, mock_export):
        """Test main dispatches to export_results."""
        with patch.object(sys, 'argv', ['snowball', 'export', '/tmp/test']):
            main()
        mock_export.assert_called_once()
