"""Tests for core snowballing functionality."""

import pytest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path
import tempfile

from snowball.snowballing import SnowballEngine
from snowball.models import Paper, PaperStatus, PaperSource, ReviewProject, FilterCriteria
from snowball.storage.json_storage import JSONStorage
from snowball.apis.aggregator import APIAggregator
from snowball.parsers.pdf_parser import PDFParser, PDFParseResult


class TestSnowballEngine:
    """Tests for SnowballEngine class."""

    @pytest.fixture
    def mock_storage(self, temp_project_dir):
        """Create a mock storage instance."""
        return JSONStorage(temp_project_dir)

    @pytest.fixture
    def mock_api(self):
        """Create a mock API aggregator."""
        return Mock(spec=APIAggregator)

    @pytest.fixture
    def mock_pdf_parser(self):
        """Create a mock PDF parser."""
        return Mock(spec=PDFParser)

    @pytest.fixture
    def engine(self, mock_storage, mock_api, mock_pdf_parser):
        """Create a snowball engine instance."""
        return SnowballEngine(mock_storage, mock_api, mock_pdf_parser)

    @pytest.fixture
    def sample_project(self):
        """Create a sample project for testing."""
        return ReviewProject(
            name="Test Project",
            max_iterations=3,
            filter_criteria=FilterCriteria(min_year=2020),
            current_iteration=0
        )

    def test_init(self, mock_storage, mock_api):
        """Test engine initialization."""
        engine = SnowballEngine(mock_storage, mock_api)
        
        assert engine.storage == mock_storage
        assert engine.api == mock_api
        assert engine.pdf_parser is not None

    def test_add_seed_from_doi(self, engine, sample_project, mock_api, mock_storage):
        """Test adding a seed paper from DOI."""
        found_paper = Paper(
            id="found-id",
            doi="10.1234/test",
            title="Found Paper",
            source=PaperSource.SEED
        )
        mock_api.search_by_doi.return_value = found_paper
        
        result = engine.add_seed_from_doi("10.1234/test", sample_project)
        
        assert result is not None
        assert result.source == PaperSource.SEED
        assert result.snowball_iteration == 0
        mock_api.search_by_doi.assert_called_once_with("10.1234/test")

    def test_add_seed_from_doi_not_found(self, engine, sample_project, mock_api):
        """Test adding seed from DOI that doesn't exist."""
        mock_api.search_by_doi.return_value = None
        
        result = engine.add_seed_from_doi("10.9999/nonexistent", sample_project)
        
        assert result is None

    def test_add_seed_from_pdf(self, engine, sample_project, mock_api, mock_pdf_parser):
        """Test adding a seed paper from PDF."""
        # Set up mock PDF parser
        parse_result = PDFParseResult()
        parse_result.title = "Parsed Paper Title"
        parse_result.authors = ["John Doe"]
        parse_result.year = 2023
        parse_result.doi = "10.1234/parsed"
        mock_pdf_parser.parse.return_value = parse_result
        
        # Set up mock API
        mock_api.identify_paper.return_value = Mock(
            semantic_scholar_id="s2-123",
            openalex_id="oa-123"
        )
        mock_api.enrich_metadata.return_value = Paper(
            id="enriched-id",
            title="Parsed Paper Title",
            doi="10.1234/parsed",
            source=PaperSource.SEED
        )
        
        # Create a dummy PDF file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            pdf_path = Path(f.name)
        
        try:
            result = engine.add_seed_from_pdf(pdf_path, sample_project)
            
            assert result is not None
            assert result.source == PaperSource.SEED
            mock_pdf_parser.parse.assert_called_once()
        finally:
            pdf_path.unlink(missing_ok=True)

    def test_add_seed_from_pdf_no_title(self, engine, sample_project, mock_pdf_parser):
        """Test adding seed from PDF with no extractable title."""
        parse_result = PDFParseResult()
        parse_result.title = None  # No title extracted
        mock_pdf_parser.parse.return_value = parse_result
        
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            pdf_path = Path(f.name)
        
        try:
            result = engine.add_seed_from_pdf(pdf_path, sample_project)
            assert result is None
        finally:
            pdf_path.unlink(missing_ok=True)


class TestSnowballEngineIteration:
    """Tests for snowballing iteration logic."""

    @pytest.fixture
    def storage_with_seeds(self, temp_project_dir):
        """Create storage with seed papers."""
        storage = JSONStorage(temp_project_dir)
        
        # Add a seed paper
        seed = Paper(
            id="seed-1",
            doi="10.1234/seed",
            title="Seed Paper",
            semantic_scholar_id="s2-seed",
            status=PaperStatus.PENDING,
            source=PaperSource.SEED,
            snowball_iteration=0
        )
        storage.save_paper(seed)
        
        # Create and save project
        project = ReviewProject(
            name="Test",
            max_iterations=2,
            filter_criteria=FilterCriteria(min_year=2020),
            seed_paper_ids=["seed-1"]
        )
        storage.save_project(project)
        
        return storage

    @pytest.fixture
    def mock_api_with_results(self):
        """Create mock API that returns references and citations."""
        api = Mock(spec=APIAggregator)
        
        ref_paper = Paper(
            id="ref-1",
            doi="10.1234/ref",
            title="Reference Paper",
            year=2021,
            source=PaperSource.BACKWARD
        )
        cit_paper = Paper(
            id="cit-1",
            doi="10.1234/cit",
            title="Citation Paper",
            year=2022,
            source=PaperSource.FORWARD
        )
        
        api.get_references.return_value = [ref_paper]
        api.get_citations.return_value = [cit_paper]
        
        return api

    def test_run_snowball_iteration_from_seeds(
        self, storage_with_seeds, mock_api_with_results
    ):
        """Test running first snowball iteration from seed papers."""
        engine = SnowballEngine(storage_with_seeds, mock_api_with_results)
        project = storage_with_seeds.load_project()
        
        stats = engine.run_snowball_iteration(project)
        
        assert stats["added"] == 2  # 1 reference + 1 citation
        assert stats["backward"] == 1
        assert stats["forward"] == 1
        
        # Project should be updated
        updated_project = storage_with_seeds.load_project()
        assert updated_project.current_iteration == 1

    def test_run_snowball_iteration_deduplicates(
        self, storage_with_seeds, mock_api_with_results
    ):
        """Test that iteration deduplicates papers by DOI."""
        # Make API return the same paper as both reference and citation
        duplicate_paper = Paper(
            id="dup-1",
            doi="10.1234/duplicate",
            title="Duplicate Paper",
            source=PaperSource.BACKWARD
        )
        mock_api_with_results.get_references.return_value = [duplicate_paper]
        mock_api_with_results.get_citations.return_value = [duplicate_paper]
        
        engine = SnowballEngine(storage_with_seeds, mock_api_with_results)
        project = storage_with_seeds.load_project()
        
        stats = engine.run_snowball_iteration(project)
        
        # Should only add 1 paper despite being returned twice
        assert stats["added"] == 1

    def test_run_snowball_iteration_applies_filters(
        self, storage_with_seeds
    ):
        """Test that iteration applies filter criteria."""
        api = Mock(spec=APIAggregator)
        
        # Return paper that doesn't meet year filter
        old_paper = Paper(
            id="old-1",
            doi="10.1234/old",
            title="Old Paper",
            year=2015,  # Before min_year of 2020
            source=PaperSource.BACKWARD
        )
        new_paper = Paper(
            id="new-1",
            doi="10.1234/new",
            title="New Paper",
            year=2022,
            source=PaperSource.BACKWARD
        )
        api.get_references.return_value = [old_paper, new_paper]
        api.get_citations.return_value = []
        
        engine = SnowballEngine(storage_with_seeds, api)
        project = storage_with_seeds.load_project()
        
        stats = engine.run_snowball_iteration(project)
        
        # Both should be added, but old one auto-excluded
        assert stats["added"] == 2
        assert stats["auto_excluded"] == 1
        assert stats["for_review"] == 1

    def test_run_snowball_iteration_no_source_papers(self, temp_project_dir):
        """Test iteration with no source papers."""
        storage = JSONStorage(temp_project_dir)
        project = ReviewProject(name="Empty", seed_paper_ids=[])
        storage.save_project(project)
        
        api = Mock(spec=APIAggregator)
        engine = SnowballEngine(storage, api)
        
        stats = engine.run_snowball_iteration(project)
        
        assert stats["added"] == 0


class TestSnowballEngineHelpers:
    """Tests for helper methods."""

    @pytest.fixture
    def engine(self, temp_project_dir):
        """Create engine with real storage."""
        storage = JSONStorage(temp_project_dir)
        api = Mock(spec=APIAggregator)
        return SnowballEngine(storage, api)

    def test_is_new_paper_by_doi(self, engine):
        """Test paper deduplication by DOI."""
        seen = {"doi:10.1234/existing"}
        
        new_paper = Paper(
            id="new",
            doi="10.5678/new",
            title="New Paper",
            source=PaperSource.SEED
        )
        existing_paper = Paper(
            id="existing",
            doi="10.1234/existing",
            title="Existing Paper",
            source=PaperSource.SEED
        )
        
        assert engine._is_new_paper(new_paper, seen) is True
        assert engine._is_new_paper(existing_paper, seen) is False

    def test_is_new_paper_by_title(self, engine):
        """Test paper deduplication by title."""
        seen = {"title:existing paper title"}
        
        new_paper = Paper(
            id="new",
            title="New Paper Title",
            source=PaperSource.SEED
        )
        existing_paper = Paper(
            id="existing",
            title="Existing Paper Title",
            source=PaperSource.SEED
        )
        
        assert engine._is_new_paper(new_paper, seen) is True
        assert engine._is_new_paper(existing_paper, seen) is False

    def test_mark_seen(self, engine):
        """Test marking papers as seen."""
        seen = set()
        
        paper = Paper(
            id="test",
            doi="10.1234/test",
            title="Test Paper",
            source=PaperSource.SEED
        )
        
        engine._mark_seen(paper, seen)
        
        assert "doi:10.1234/test" in seen
        assert "title:test paper" in seen

    def test_should_continue_snowballing_max_iterations(self, temp_project_dir):
        """Test that snowballing stops at max iterations."""
        storage = JSONStorage(temp_project_dir)
        project = ReviewProject(
            name="Test",
            max_iterations=2,
            current_iteration=2,
            seed_paper_ids=["seed-1"]
        )
        storage.save_project(project)
        
        api = Mock(spec=APIAggregator)
        engine = SnowballEngine(storage, api)
        
        assert engine.should_continue_snowballing(project) is False

    def test_should_continue_snowballing_no_seeds(self, temp_project_dir):
        """Test that snowballing stops with no seeds."""
        storage = JSONStorage(temp_project_dir)
        project = ReviewProject(
            name="Test",
            max_iterations=2,
            current_iteration=0,
            seed_paper_ids=[]
        )
        storage.save_project(project)
        
        api = Mock(spec=APIAggregator)
        engine = SnowballEngine(storage, api)
        
        assert engine.should_continue_snowballing(project) is False

    def test_should_continue_snowballing_with_seeds(self, temp_project_dir):
        """Test that snowballing continues with seeds."""
        storage = JSONStorage(temp_project_dir)
        project = ReviewProject(
            name="Test",
            max_iterations=2,
            current_iteration=0,
            seed_paper_ids=["seed-1"]
        )
        storage.save_project(project)
        
        api = Mock(spec=APIAggregator)
        engine = SnowballEngine(storage, api)
        
        assert engine.should_continue_snowballing(project) is True


class TestSnowballEngineReview:
    """Tests for review-related functionality."""

    @pytest.fixture
    def storage_with_papers(self, temp_project_dir, sample_papers):
        """Create storage with papers."""
        storage = JSONStorage(temp_project_dir)
        for paper in sample_papers:
            storage.save_paper(paper)
        return storage

    def test_get_papers_for_review_all_pending(self, storage_with_papers):
        """Test getting all pending papers for review."""
        api = Mock(spec=APIAggregator)
        engine = SnowballEngine(storage_with_papers, api)
        
        papers = engine.get_papers_for_review()
        
        assert all(p.status == PaperStatus.PENDING for p in papers)

    def test_get_papers_for_review_by_iteration(self, storage_with_papers):
        """Test getting papers for review by iteration."""
        api = Mock(spec=APIAggregator)
        engine = SnowballEngine(storage_with_papers, api)
        
        papers = engine.get_papers_for_review(iteration=1)
        
        # Should only return pending papers from iteration 1
        for paper in papers:
            assert paper.snowball_iteration == 1
            assert paper.status == PaperStatus.PENDING

    def test_update_paper_review(self, storage_with_papers, sample_paper):
        """Test updating a paper's review status."""
        storage_with_papers.save_paper(sample_paper)
        
        api = Mock(spec=APIAggregator)
        engine = SnowballEngine(storage_with_papers, api)
        
        engine.update_paper_review(
            sample_paper.id,
            PaperStatus.INCLUDED,
            "Good paper",
            ["relevant"]
        )
        
        updated = storage_with_papers.load_paper(sample_paper.id)
        assert updated.status == PaperStatus.INCLUDED
        assert updated.notes == "Good paper"
        assert "relevant" in updated.tags
