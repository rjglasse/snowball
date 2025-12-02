"""Tests for Pydantic data models."""

import pytest
from datetime import datetime

from snowball.models import (
    Paper,
    Author,
    Venue,
    PaperStatus,
    PaperSource,
    FilterCriteria,
    ReviewProject,
)


class TestPaperStatus:
    """Tests for PaperStatus enum."""

    def test_enum_values(self):
        """Test that PaperStatus has correct values."""
        assert PaperStatus.PENDING.value == "pending"
        assert PaperStatus.INCLUDED.value == "included"
        assert PaperStatus.EXCLUDED.value == "excluded"
        assert PaperStatus.MAYBE.value == "maybe"

    def test_enum_is_string(self):
        """Test that PaperStatus values are strings."""
        for status in PaperStatus:
            assert isinstance(status.value, str)


class TestPaperSource:
    """Tests for PaperSource enum."""

    def test_enum_values(self):
        """Test that PaperSource has correct values."""
        assert PaperSource.SEED.value == "seed"
        assert PaperSource.BACKWARD.value == "backward"
        assert PaperSource.FORWARD.value == "forward"


class TestAuthor:
    """Tests for Author model."""

    def test_create_author_with_name_only(self):
        """Test creating author with only name."""
        author = Author(name="John Doe")
        assert author.name == "John Doe"
        assert author.affiliations is None

    def test_create_author_with_affiliations(self):
        """Test creating author with affiliations."""
        author = Author(name="John Doe", affiliations=["MIT", "Harvard"])
        assert author.name == "John Doe"
        assert author.affiliations == ["MIT", "Harvard"]

    def test_author_serialization(self):
        """Test that author can be serialized to dict."""
        author = Author(name="John Doe", affiliations=["MIT"])
        data = author.model_dump()
        assert data["name"] == "John Doe"
        assert data["affiliations"] == ["MIT"]


class TestVenue:
    """Tests for Venue model."""

    def test_create_venue_minimal(self):
        """Test creating venue with minimal fields."""
        venue = Venue()
        assert venue.name is None
        assert venue.type is None
        assert venue.year is None

    def test_create_venue_full(self):
        """Test creating venue with all fields."""
        venue = Venue(
            name="Nature",
            type="journal",
            year=2023,
            volume="123",
            issue="4",
            pages="100-110"
        )
        assert venue.name == "Nature"
        assert venue.type == "journal"
        assert venue.year == 2023
        assert venue.volume == "123"
        assert venue.issue == "4"
        assert venue.pages == "100-110"


class TestPaper:
    """Tests for Paper model."""

    def test_create_paper_minimal(self):
        """Test creating paper with only required fields."""
        paper = Paper(
            id="test-id",
            title="Test Title",
            source=PaperSource.SEED
        )
        assert paper.id == "test-id"
        assert paper.title == "Test Title"
        assert paper.source == PaperSource.SEED
        assert paper.status == PaperStatus.PENDING  # Default

    def test_create_paper_full(self, sample_paper):
        """Test creating paper with all fields."""
        assert sample_paper.id == "test-paper-id-123"
        assert sample_paper.doi == "10.1234/test.doi"
        assert sample_paper.arxiv_id == "2301.00001"
        assert sample_paper.title == "A Test Paper Title"
        assert len(sample_paper.authors) == 1
        assert sample_paper.year == 2023
        assert sample_paper.citation_count == 100
        assert sample_paper.status == PaperStatus.PENDING
        assert sample_paper.source == PaperSource.SEED

    def test_paper_default_values(self):
        """Test that paper has correct default values."""
        paper = Paper(
            id="test-id",
            title="Test Title",
            source=PaperSource.SEED
        )
        assert paper.authors == []
        assert paper.references == []
        assert paper.citations == []
        assert paper.tags == []
        assert paper.notes == ""
        assert paper.snowball_iteration == 0
        assert paper.raw_data == {}

    def test_paper_serialization(self, sample_paper):
        """Test that paper can be serialized to dict."""
        data = sample_paper.model_dump(mode='json')
        assert isinstance(data, dict)
        assert data["id"] == "test-paper-id-123"
        assert data["title"] == "A Test Paper Title"
        # Check enum values are serialized as strings
        assert data["status"] == "pending"
        assert data["source"] == "seed"

    def test_paper_deserialization(self, sample_paper):
        """Test that paper can be deserialized from dict."""
        data = sample_paper.model_dump(mode='json')
        restored_paper = Paper.model_validate(data)
        assert restored_paper.id == sample_paper.id
        assert restored_paper.title == sample_paper.title
        assert restored_paper.status == sample_paper.status

    def test_paper_with_none_values(self):
        """Test paper with optional fields as None."""
        paper = Paper(
            id="test-id",
            title="Test Title",
            source=PaperSource.SEED,
            year=None,
            citation_count=None,
            abstract=None,
            doi=None
        )
        assert paper.year is None
        assert paper.citation_count is None


class TestFilterCriteria:
    """Tests for FilterCriteria model."""

    def test_create_empty_criteria(self):
        """Test creating empty filter criteria."""
        criteria = FilterCriteria()
        assert criteria.min_year is None
        assert criteria.max_year is None
        assert criteria.keywords == []
        assert criteria.excluded_keywords == []

    def test_create_criteria_with_years(self):
        """Test creating criteria with year range."""
        criteria = FilterCriteria(min_year=2020, max_year=2024)
        assert criteria.min_year == 2020
        assert criteria.max_year == 2024

    def test_create_criteria_with_keywords(self):
        """Test creating criteria with keywords."""
        criteria = FilterCriteria(
            keywords=["machine learning", "AI"],
            excluded_keywords=["survey"]
        )
        assert "machine learning" in criteria.keywords
        assert "survey" in criteria.excluded_keywords

    def test_create_criteria_full(self, sample_filter_criteria):
        """Test creating criteria with all fields."""
        assert sample_filter_criteria.min_year == 2020
        assert sample_filter_criteria.max_year == 2024
        assert sample_filter_criteria.min_citations == 10
        assert sample_filter_criteria.max_citations == 1000
        assert len(sample_filter_criteria.keywords) == 2
        assert sample_filter_criteria.min_influential_citations == 5


class TestReviewProject:
    """Tests for ReviewProject model."""

    def test_create_project_minimal(self):
        """Test creating project with only name."""
        project = ReviewProject(name="Test Project")
        assert project.name == "Test Project"
        assert project.description == ""
        assert project.max_iterations == 1  # Default
        assert project.current_iteration == 0

    def test_create_project_full(self, sample_project):
        """Test creating project with all fields."""
        assert sample_project.name == "Test Project"
        assert sample_project.description == "A test systematic literature review project"
        assert sample_project.max_iterations == 3
        assert sample_project.current_iteration == 1
        assert len(sample_project.seed_paper_ids) == 1

    def test_project_created_at_default(self):
        """Test that project has created_at timestamp."""
        project = ReviewProject(name="Test")
        assert project.created_at is not None
        assert isinstance(project.created_at, datetime)

    def test_project_serialization(self, sample_project):
        """Test that project can be serialized to dict."""
        data = sample_project.model_dump(mode='json')
        assert isinstance(data, dict)
        assert data["name"] == "Test Project"
        assert data["max_iterations"] == 3

    def test_project_deserialization(self, sample_project):
        """Test that project can be deserialized from dict."""
        data = sample_project.model_dump(mode='json')
        restored = ReviewProject.model_validate(data)
        assert restored.name == sample_project.name
        assert restored.max_iterations == sample_project.max_iterations
