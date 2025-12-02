"""Tests for CSV export functionality."""

import pytest
from pathlib import Path
import tempfile

from snowball.exporters.csv_exporter import CSVExporter
from snowball.models import Paper, Author, Venue, PaperStatus, PaperSource


class TestCSVExporter:
    """Tests for CSVExporter class."""

    @pytest.fixture
    def exporter(self):
        """Create a CSV exporter instance."""
        return CSVExporter()

    @pytest.fixture
    def output_path(self):
        """Create a temporary output path."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            yield Path(f.name)

    @pytest.fixture
    def papers_for_export(self):
        """Create papers for export testing."""
        return [
            Paper(
                id="p1",
                doi="10.1234/paper1",
                title="Machine Learning Paper",
                authors=[Author(name="John Doe"), Author(name="Jane Smith")],
                year=2023,
                venue=Venue(name="Nature", type="journal"),
                citation_count=100,
                status=PaperStatus.INCLUDED,
                source=PaperSource.SEED,
                snowball_iteration=0,
                notes="Important paper"
            ),
            Paper(
                id="p2",
                title="Deep Learning Paper",
                authors=[Author(name="Bob Johnson")],
                year=2022,
                citation_count=50,
                status=PaperStatus.PENDING,
                source=PaperSource.BACKWARD,
                snowball_iteration=1
            ),
            Paper(
                id="p3",
                title="Excluded Paper",
                status=PaperStatus.EXCLUDED,
                source=PaperSource.FORWARD,
                snowball_iteration=1
            ),
        ]

    def test_export_creates_file(self, exporter, papers_for_export, output_path):
        """Test that export creates a CSV file."""
        exporter.export(papers_for_export, output_path, only_included=False)
        assert output_path.exists()

    def test_export_csv_content(self, exporter, papers_for_export, output_path):
        """Test that CSV contains expected content."""
        exporter.export(papers_for_export, output_path, only_included=False)
        
        content = output_path.read_text()
        # Check headers
        assert "Title" in content
        assert "Authors" in content
        assert "Year" in content
        assert "Status" in content
        
        # Check data
        assert "Machine Learning Paper" in content
        assert "Deep Learning Paper" in content

    def test_export_only_included(self, exporter, papers_for_export, output_path):
        """Test exporting only included papers."""
        exporter.export(papers_for_export, output_path, only_included=True)
        
        content = output_path.read_text()
        assert "Machine Learning Paper" in content
        assert "Deep Learning Paper" not in content
        assert "Excluded Paper" not in content

    def test_export_all_papers(self, exporter, papers_for_export, output_path):
        """Test exporting all papers."""
        exporter.export(papers_for_export, output_path, only_included=False)
        
        content = output_path.read_text()
        assert "Machine Learning Paper" in content
        assert "Deep Learning Paper" in content
        assert "Excluded Paper" in content

    def test_export_include_all_fields(self, exporter, output_path):
        """Test exporting with all fields."""
        paper = Paper(
            id="p1",
            doi="10.1234/paper1",
            arxiv_id="2301.00001",
            semantic_scholar_id="abc123",
            openalex_id="W123",
            pmid="12345",
            title="Test Paper",
            abstract="Test abstract text",
            influential_citation_count=10,
            status=PaperStatus.INCLUDED,
            source=PaperSource.SEED,
            tags=["ml", "ai"],
            pdf_path="/path/to/paper.pdf"
        )
        exporter.export([paper], output_path, only_included=False, include_all_fields=True)
        
        content = output_path.read_text()
        assert "Abstract" in content
        assert "ArXiv_ID" in content
        assert "Semantic_Scholar_ID" in content
        assert "Tags" in content

    def test_export_empty_list(self, exporter, output_path):
        """Test exporting an empty list."""
        exporter.export([], output_path, only_included=False)
        assert output_path.exists()


class TestCSVExporterFormatting:
    """Tests for CSV formatting helper methods."""

    @pytest.fixture
    def exporter(self):
        """Create a CSV exporter instance."""
        return CSVExporter()

    def test_format_authors_multiple(self, exporter):
        """Test formatting multiple authors."""
        paper = Paper(
            id="test",
            title="Test",
            authors=[
                Author(name="John Doe"),
                Author(name="Jane Smith"),
                Author(name="Bob Johnson")
            ],
            source=PaperSource.SEED
        )
        result = exporter._format_authors(paper)
        assert result == "John Doe; Jane Smith; Bob Johnson"

    def test_format_authors_single(self, exporter):
        """Test formatting single author."""
        paper = Paper(
            id="test",
            title="Test",
            authors=[Author(name="John Doe")],
            source=PaperSource.SEED
        )
        result = exporter._format_authors(paper)
        assert result == "John Doe"

    def test_format_authors_empty(self, exporter):
        """Test formatting no authors."""
        paper = Paper(
            id="test",
            title="Test",
            authors=[],
            source=PaperSource.SEED
        )
        result = exporter._format_authors(paper)
        assert result == ""

    def test_format_venue_with_name(self, exporter):
        """Test formatting venue with name."""
        paper = Paper(
            id="test",
            title="Test",
            venue=Venue(name="Nature"),
            source=PaperSource.SEED
        )
        result = exporter._format_venue(paper)
        assert result == "Nature"

    def test_format_venue_with_different_year(self, exporter):
        """Test formatting venue when venue year differs from paper year."""
        paper = Paper(
            id="test",
            title="Test",
            year=2023,
            venue=Venue(name="NeurIPS", year=2022),
            source=PaperSource.SEED
        )
        result = exporter._format_venue(paper)
        assert "NeurIPS" in result
        assert "2022" in result

    def test_format_venue_no_venue(self, exporter):
        """Test formatting when no venue."""
        paper = Paper(
            id="test",
            title="Test",
            source=PaperSource.SEED
        )
        result = exporter._format_venue(paper)
        assert result == ""


class TestCSVExporterStatistics:
    """Tests for CSV statistics generation."""

    @pytest.fixture
    def exporter(self):
        """Create a CSV exporter instance."""
        return CSVExporter()

    def test_generate_statistics(self, exporter, sample_papers):
        """Test generating statistics from papers."""
        stats = exporter._generate_statistics(sample_papers)
        
        # Check that stats DataFrame is created
        assert stats is not None
        assert "Value" in stats.columns

    def test_generate_statistics_by_status(self, exporter, sample_papers):
        """Test statistics count papers by status."""
        stats = exporter._generate_statistics(sample_papers)
        
        # Check status counts
        index_labels = [str(i) for i in stats.index]
        assert any("included" in label.lower() for label in index_labels)
        assert any("excluded" in label.lower() for label in index_labels)

    def test_generate_statistics_year_range(self, exporter):
        """Test statistics include year range."""
        papers = [
            Paper(id="p1", title="Old Paper", year=2020, source=PaperSource.SEED),
            Paper(id="p2", title="New Paper", year=2023, source=PaperSource.SEED),
        ]
        stats = exporter._generate_statistics(papers)
        
        # Check year stats
        assert "Year - Earliest" in stats.index
        assert "Year - Latest" in stats.index
        assert stats.loc["Year - Earliest", "Value"] == 2020
        assert stats.loc["Year - Latest", "Value"] == 2023

    def test_generate_statistics_citation_stats(self, exporter):
        """Test statistics include citation stats."""
        papers = [
            Paper(
                id="p1",
                title="Paper 1",
                citation_count=100,
                source=PaperSource.SEED
            ),
            Paper(
                id="p2",
                title="Paper 2",
                citation_count=200,
                source=PaperSource.SEED
            ),
        ]
        stats = exporter._generate_statistics(papers)
        
        # Check citation stats
        assert "Citations - Mean" in stats.index
        assert "Citations - Max" in stats.index
        assert stats.loc["Citations - Max", "Value"] == 200

    def test_generate_statistics_empty_papers(self, exporter):
        """Test statistics with no papers."""
        stats = exporter._generate_statistics([])
        assert stats is not None
