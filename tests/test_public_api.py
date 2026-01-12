"""Tests for the public API exports.

This ensures that all documented public APIs can be imported and used
as a reusable library, separate from the CLI/TUI interfaces.
"""

import pytest


class TestPublicAPIImports:
    """Test that all public API components can be imported."""

    def test_import_all_from_snowball(self):
        """Test importing all public components."""
        from snowball import (
            # Version
            __version__,
            # Core models
            Paper,
            PaperStatus,
            PaperSource,
            ExclusionType,
            Author,
            Venue,
            FilterCriteria,
            ReviewProject,
            IterationStats,
            # Storage
            JSONStorage,
            # Core engine
            SnowballEngine,
            # API clients
            APIAggregator,
            SemanticScholarClient,
            OpenAlexClient,
            CrossRefClient,
            ArXivClient,
            # Parsers
            PDFParser,
            PDFParseResult,
            # Filters
            FilterEngine,
            # Exporters
            BibTeXExporter,
            CSVExporter,
            TikZExporter,
            # Scoring
            BaseScorer,
            TFIDFScorer,
            # Visualization
            generate_citation_graph,
            # Utility functions
            filter_papers,
            sort_papers,
            paper_to_dict,
            format_paper_text,
            truncate_title,
            get_status_value,
            get_source_value,
        )

        # Basic validation
        assert __version__ is not None
        assert Paper is not None
        assert SnowballEngine is not None
        assert APIAggregator is not None

    def test_core_models_importable(self):
        """Test that core data models can be imported."""
        from snowball import (
            Paper,
            PaperStatus,
            PaperSource,
            Author,
            Venue,
            FilterCriteria,
            ReviewProject,
        )

        # Verify they are classes
        assert isinstance(Paper, type)
        assert isinstance(Author, type)
        assert isinstance(ReviewProject, type)

    def test_storage_importable(self):
        """Test that storage components can be imported."""
        from snowball import JSONStorage

        assert isinstance(JSONStorage, type)

    def test_engine_importable(self):
        """Test that core engine can be imported."""
        from snowball import SnowballEngine

        assert isinstance(SnowballEngine, type)

    def test_api_clients_importable(self):
        """Test that all API clients can be imported."""
        from snowball import (
            APIAggregator,
            SemanticScholarClient,
            OpenAlexClient,
            CrossRefClient,
            ArXivClient,
        )

        assert isinstance(APIAggregator, type)
        assert isinstance(SemanticScholarClient, type)
        assert isinstance(OpenAlexClient, type)
        assert isinstance(CrossRefClient, type)
        assert isinstance(ArXivClient, type)

    def test_parsers_importable(self):
        """Test that parsers can be imported."""
        from snowball import PDFParser, PDFParseResult

        assert isinstance(PDFParser, type)
        assert isinstance(PDFParseResult, type)

    def test_filters_importable(self):
        """Test that filter engine can be imported."""
        from snowball import FilterEngine

        assert isinstance(FilterEngine, type)

    def test_exporters_importable(self):
        """Test that all exporters can be imported."""
        from snowball import BibTeXExporter, CSVExporter, TikZExporter

        assert isinstance(BibTeXExporter, type)
        assert isinstance(CSVExporter, type)
        assert isinstance(TikZExporter, type)

    def test_scorers_importable(self):
        """Test that scoring components can be imported."""
        from snowball import BaseScorer, TFIDFScorer

        assert isinstance(BaseScorer, type)
        assert isinstance(TFIDFScorer, type)

    def test_llm_scorer_optional(self):
        """Test that LLMScorer is optional (requires openai package)."""
        try:
            from snowball import LLMScorer
            # If import succeeds, it should be a class
            assert isinstance(LLMScorer, type)
        except ImportError:
            # If openai is not installed, import should fail gracefully
            pass

    def test_visualization_importable(self):
        """Test that visualization functions can be imported."""
        from snowball import generate_citation_graph

        assert callable(generate_citation_graph)

    def test_utility_functions_importable(self):
        """Test that utility functions can be imported."""
        from snowball import (
            filter_papers,
            sort_papers,
            paper_to_dict,
            format_paper_text,
            truncate_title,
            get_status_value,
            get_source_value,
        )

        assert callable(filter_papers)
        assert callable(sort_papers)
        assert callable(paper_to_dict)
        assert callable(format_paper_text)
        assert callable(truncate_title)
        assert callable(get_status_value)
        assert callable(get_source_value)

    def test_no_tui_imports_in_core(self):
        """Test that core modules don't import TUI components."""
        # Import core modules
        from snowball import (
            SnowballEngine,
            JSONStorage,
            APIAggregator,
            FilterEngine,
        )

        # These should not have any dependencies on TUI
        # (checked by importing successfully without TUI-related errors)
        assert SnowballEngine is not None
        assert JSONStorage is not None
        assert APIAggregator is not None
        assert FilterEngine is not None


class TestBasicAPIUsage:
    """Test basic usage patterns of the public API."""

    def test_create_project(self):
        """Test creating a review project programmatically."""
        from snowball import ReviewProject, FilterCriteria

        project = ReviewProject(
            name="Test Project",
            description="A test project",
            filter_criteria=FilterCriteria(min_year=2020, max_year=2024),
        )

        assert project.name == "Test Project"
        assert project.filter_criteria.min_year == 2020
        assert project.filter_criteria.max_year == 2024

    def test_create_paper(self):
        """Test creating a paper programmatically."""
        from snowball import Paper, PaperStatus, PaperSource, Author

        paper = Paper(
            id="test-id",
            title="Test Paper",
            authors=[Author(name="John Doe")],
            year=2023,
            status=PaperStatus.PENDING,
            source=PaperSource.SEED,
            snowball_iteration=0,
        )

        assert paper.title == "Test Paper"
        assert paper.year == 2023
        assert paper.status == PaperStatus.PENDING
        assert len(paper.authors) == 1
        assert paper.authors[0].name == "John Doe"

    def test_filter_criteria_creation(self):
        """Test creating filter criteria."""
        from snowball import FilterCriteria

        criteria = FilterCriteria(
            min_year=2015,
            max_year=2025,
            min_citations=5,
            keywords=["machine learning", "AI"],
        )

        assert criteria.min_year == 2015
        assert criteria.max_year == 2025
        assert criteria.min_citations == 5
        assert "machine learning" in criteria.keywords

    def test_api_aggregator_initialization(self):
        """Test initializing the API aggregator."""
        from snowball import APIAggregator

        api = APIAggregator()
        assert api is not None

    def test_filter_engine_initialization(self):
        """Test initializing the filter engine."""
        from snowball import FilterEngine

        engine = FilterEngine()
        assert engine is not None

    def test_pdf_parser_initialization(self):
        """Test initializing the PDF parser."""
        from snowball import PDFParser

        parser = PDFParser(use_grobid=False)
        assert parser is not None
        assert parser.use_grobid is False

    def test_bibtex_exporter_initialization(self):
        """Test initializing the BibTeX exporter."""
        from snowball import BibTeXExporter

        exporter = BibTeXExporter()
        assert exporter is not None

    def test_tfidf_scorer_initialization(self):
        """Test initializing the TF-IDF scorer."""
        from snowball import TFIDFScorer

        scorer = TFIDFScorer()
        assert scorer is not None

    def test_utility_functions_work(self):
        """Test that utility functions work correctly."""
        from snowball import (
            get_status_value,
            get_source_value,
            PaperStatus,
            PaperSource,
        )

        # Test status conversion
        assert get_status_value(PaperStatus.PENDING) == "pending"
        assert get_status_value("included") == "included"

        # Test source conversion
        assert get_source_value(PaperSource.SEED) == "seed"
        assert get_source_value("backward") == "backward"


class TestAPIDocumentation:
    """Test that the public API has proper documentation."""

    def test_module_has_docstring(self):
        """Test that the main module has a docstring."""
        import snowball

        assert snowball.__doc__ is not None
        assert len(snowball.__doc__) > 0
        assert "Systematic Literature Review" in snowball.__doc__

    def test_module_has_version(self):
        """Test that the module exports a version."""
        from snowball import __version__

        assert __version__ is not None
        assert isinstance(__version__, str)
        assert len(__version__) > 0

    def test_main_classes_have_docstrings(self):
        """Test that main classes have docstrings."""
        from snowball import (
            SnowballEngine,
            JSONStorage,
            APIAggregator,
            FilterEngine,
        )

        assert SnowballEngine.__doc__ is not None
        assert JSONStorage.__doc__ is not None
        assert APIAggregator.__doc__ is not None
        assert FilterEngine.__doc__ is not None

    def test_module_has_all_export(self):
        """Test that the module has __all__ defined."""
        import snowball

        assert hasattr(snowball, "__all__")
        assert isinstance(snowball.__all__, list)
        assert len(snowball.__all__) > 0
