"""Snowball - Systematic Literature Review using Snowballing.

This package provides a reusable Python API for conducting systematic literature
reviews using the snowballing methodology. The core functionality is separated from
the user interface (CLI/TUI) to allow integration into custom workflows.

Core Components
---------------
- **SnowballEngine**: Main engine for running snowballing iterations
- **JSONStorage**: Storage backend for projects and papers
- **APIAggregator**: Unified interface to multiple academic APIs

Data Models
-----------
- **Paper**: Represents a scholarly paper with metadata
- **ReviewProject**: Represents a review project with configuration
- **FilterCriteria**: Criteria for filtering papers
- **Author**, **Venue**: Supporting data structures

API Clients
-----------
- **SemanticScholarClient**: Semantic Scholar API
- **OpenAlexClient**: OpenAlex API
- **CrossRefClient**: CrossRef API
- **ArXivClient**: arXiv API

Utilities
---------
- **PDFParser**: Extract metadata from PDF files
- **FilterEngine**: Apply filters to papers
- **BibTeXExporter**, **CSVExporter**, **TikZExporter**: Export results
- **TFIDFScorer**, **LLMScorer**: Relevance scoring

Example Usage
-------------
    >>> from snowball import SnowballEngine, JSONStorage, APIAggregator, ReviewProject, FilterCriteria
    >>> 
    >>> # Initialize components
    >>> storage = JSONStorage("/path/to/project")
    >>> api = APIAggregator()
    >>> engine = SnowballEngine(storage, api)
    >>> 
    >>> # Create project
    >>> project = ReviewProject(
    ...     name="My Review",
    ...     filter_criteria=FilterCriteria(min_year=2020)
    ... )
    >>> storage.save_project(project)
    >>> 
    >>> # Add seed paper
    >>> paper = engine.add_seed_from_doi("10.1234/example.doi", project)
    >>> 
    >>> # Run snowballing
    >>> stats = engine.run_snowball_iteration(project, direction="both")
    >>> print(f"Found {stats['added']} papers")
"""

__version__ = "0.1.0"

# Core models
from .models import (
    Paper,
    PaperStatus,
    PaperSource,
    ExclusionType,
    Author,
    Venue,
    FilterCriteria,
    ReviewProject,
    IterationStats,
)

# Storage
from .storage.json_storage import JSONStorage

# Core engine
from .snowballing import SnowballEngine

# API clients
from .apis.aggregator import APIAggregator
from .apis.semantic_scholar import SemanticScholarClient
from .apis.openalex import OpenAlexClient
from .apis.crossref import CrossRefClient
from .apis.arxiv import ArXivClient

# Parsers
from .parsers.pdf_parser import PDFParser, PDFParseResult

# Filters
from .filters.filter_engine import FilterEngine

# Exporters
from .exporters.bibtex import BibTeXExporter
from .exporters.csv_exporter import CSVExporter
from .exporters.tikz import TikZExporter

# Scoring
from .scoring.base import BaseScorer
from .scoring.tfidf_scorer import TFIDFScorer

# Optional: LLM Scorer (requires openai package)
try:
    from .scoring.llm_scorer import LLMScorer
    _has_llm_scorer = True
except ImportError as e:
    # Only catch missing openai package, re-raise other errors
    if "openai" in str(e):
        LLMScorer = None  # type: ignore
        _has_llm_scorer = False
    else:
        # Re-raise if it's a different import error
        raise

# Visualization
from .visualization import generate_citation_graph

# Utility functions
from .paper_utils import (
    filter_papers,
    sort_papers,
    paper_to_dict,
    format_paper_text,
    truncate_title,
    get_status_value,
    get_source_value,
)

__all__ = [
    # Version
    "__version__",
    # Core models
    "Paper",
    "PaperStatus",
    "PaperSource",
    "ExclusionType",
    "Author",
    "Venue",
    "FilterCriteria",
    "ReviewProject",
    "IterationStats",
    # Storage
    "JSONStorage",
    # Core engine
    "SnowballEngine",
    # API clients
    "APIAggregator",
    "SemanticScholarClient",
    "OpenAlexClient",
    "CrossRefClient",
    "ArXivClient",
    # Parsers
    "PDFParser",
    "PDFParseResult",
    # Filters
    "FilterEngine",
    # Exporters
    "BibTeXExporter",
    "CSVExporter",
    "TikZExporter",
    # Scoring
    "BaseScorer",
    "TFIDFScorer",
    # Visualization
    "generate_citation_graph",
    # Utility functions
    "filter_papers",
    "sort_papers",
    "paper_to_dict",
    "format_paper_text",
    "truncate_title",
    "get_status_value",
    "get_source_value",
]

# Add LLMScorer to __all__ if available
if _has_llm_scorer:
    __all__.append("LLMScorer")


def register_commands(parent_app):
    """Register snowball commands with a parent Typer app.

    This function is called by the scholar CLI to add snowball as a subcommand.
    Usage: scholar snowball <command>

    Args:
        parent_app: The parent Typer application to register commands with.
    """
    from snowball.cli import app as snowball_app

    parent_app.add_typer(
        snowball_app,
        name="snowball",
        help="Systematic literature review using snowballing.",
    )
