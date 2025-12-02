"""Shared pytest fixtures for Snowball SLR tests."""

import pytest
from pathlib import Path
import tempfile
import shutil

from snowball.models import (
    Paper,
    Author,
    Venue,
    PaperStatus,
    PaperSource,
    FilterCriteria,
    ReviewProject,
)
from snowball.storage.json_storage import JSONStorage


@pytest.fixture
def sample_author():
    """Create a sample author."""
    return Author(name="John Doe", affiliations=["MIT"])


@pytest.fixture
def sample_venue():
    """Create a sample venue."""
    return Venue(
        name="Nature",
        type="journal",
        year=2023,
        volume="123",
        issue="4",
        pages="100-110"
    )


@pytest.fixture
def sample_paper(sample_author, sample_venue):
    """Create a sample paper with all fields populated."""
    return Paper(
        id="test-paper-id-123",
        doi="10.1234/test.doi",
        arxiv_id="2301.00001",
        pmid="12345678",
        semantic_scholar_id="abc123",
        openalex_id="W1234567890",
        title="A Test Paper Title",
        authors=[sample_author],
        year=2023,
        abstract="This is a test abstract for the paper.",
        venue=sample_venue,
        citation_count=100,
        influential_citation_count=10,
        references=["ref-1", "ref-2"],
        citations=["cit-1", "cit-2"],
        status=PaperStatus.PENDING,
        source=PaperSource.SEED,
        source_paper_id=None,
        snowball_iteration=0,
        notes="Test notes",
        tags=["machine-learning", "test"],
        pdf_path="/path/to/paper.pdf",
        raw_data={"key": "value"}
    )


@pytest.fixture
def sample_paper_minimal():
    """Create a minimal paper with only required fields."""
    return Paper(
        id="minimal-paper-id",
        title="Minimal Paper",
        source=PaperSource.SEED
    )


@pytest.fixture
def sample_papers():
    """Create a list of sample papers for testing."""
    papers = []
    
    # Paper with all fields
    papers.append(Paper(
        id="paper-1",
        doi="10.1234/paper1",
        title="Machine Learning in Healthcare",
        authors=[Author(name="Alice Smith")],
        year=2022,
        abstract="This paper discusses machine learning applications in healthcare.",
        venue=Venue(name="Nature Medicine", type="journal"),
        citation_count=150,
        status=PaperStatus.INCLUDED,
        source=PaperSource.SEED,
        snowball_iteration=0
    ))
    
    # Paper with some fields
    papers.append(Paper(
        id="paper-2",
        doi="10.1234/paper2",
        title="Deep Learning Approaches",
        authors=[Author(name="Bob Johnson")],
        year=2021,
        venue=Venue(name="NeurIPS", type="conference"),
        citation_count=50,
        status=PaperStatus.PENDING,
        source=PaperSource.BACKWARD,
        source_paper_id="paper-1",
        snowball_iteration=1
    ))
    
    # Paper with minimal fields
    papers.append(Paper(
        id="paper-3",
        title="Unknown Title Paper",
        status=PaperStatus.EXCLUDED,
        source=PaperSource.FORWARD,
        source_paper_id="paper-1",
        snowball_iteration=1,
        notes="Auto-excluded by filters"
    ))
    
    # Paper with None values
    papers.append(Paper(
        id="paper-4",
        title="Paper with None Values",
        year=None,
        citation_count=None,
        status=PaperStatus.MAYBE,
        source=PaperSource.BACKWARD,
        snowball_iteration=2
    ))
    
    return papers


@pytest.fixture
def sample_filter_criteria():
    """Create sample filter criteria."""
    return FilterCriteria(
        min_year=2020,
        max_year=2024,
        min_citations=10,
        max_citations=1000,
        keywords=["machine learning", "AI"],
        excluded_keywords=["survey", "review"],
        venue_types=["journal", "conference"],
        min_influential_citations=5
    )


@pytest.fixture
def sample_project():
    """Create a sample review project."""
    return ReviewProject(
        name="Test Project",
        description="A test systematic literature review project",
        max_iterations=3,
        filter_criteria=FilterCriteria(min_year=2020),
        seed_paper_ids=["paper-1"],
        total_papers=4,
        papers_by_status={"included": 1, "excluded": 1, "pending": 1, "maybe": 1},
        current_iteration=1
    )


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory for testing storage."""
    temp_dir = tempfile.mkdtemp(prefix="snowball_test_")
    yield Path(temp_dir)
    # Cleanup after test
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def storage(temp_project_dir):
    """Create a JSONStorage instance with a temporary directory."""
    return JSONStorage(temp_project_dir)


@pytest.fixture
def storage_with_papers(storage, sample_papers):
    """Create a storage instance with sample papers pre-loaded."""
    for paper in sample_papers:
        storage.save_paper(paper)
    return storage


@pytest.fixture
def storage_with_project(storage, sample_project, sample_papers):
    """Create a storage instance with a project and papers."""
    storage.save_project(sample_project)
    for paper in sample_papers:
        storage.save_paper(paper)
    return storage
