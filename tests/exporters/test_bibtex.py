"""Tests for BibTeX export functionality."""

import pytest

from snowball.exporters.bibtex import BibTeXExporter
from snowball.models import Paper, Author, Venue, PaperStatus, PaperSource


class TestBibTeXExporter:
    """Tests for BibTeXExporter class."""

    @pytest.fixture
    def exporter(self):
        """Create a BibTeX exporter instance."""
        return BibTeXExporter()

    @pytest.fixture
    def paper_for_export(self):
        """Create a paper with all fields for export testing."""
        return Paper(
            id="test-id",
            doi="10.1234/test.doi",
            arxiv_id="2301.00001",
            pmid="12345678",
            title="A Comprehensive Study of Machine Learning",
            authors=[
                Author(name="John Doe"),
                Author(name="Jane Smith"),
            ],
            year=2023,
            abstract="This paper presents a comprehensive study.",
            venue=Venue(
                name="Nature Machine Intelligence",
                type="journal",
                volume="5",
                issue="3",
                pages="100-120"
            ),
            status=PaperStatus.INCLUDED,
            source=PaperSource.SEED
        )

    def test_export_empty_list(self, exporter):
        """Test exporting an empty list of papers."""
        result = exporter.export([], only_included=False)
        assert result == ""

    def test_export_single_paper(self, exporter, paper_for_export):
        """Test exporting a single paper."""
        result = exporter.export([paper_for_export], only_included=True)
        
        assert "@article{" in result
        assert "John Doe and Jane Smith" in result
        assert "A Comprehensive Study of Machine Learning" in result
        assert "2023" in result

    def test_export_filters_by_included(self, exporter):
        """Test that only_included=True filters out non-included papers."""
        papers = [
            Paper(
                id="p1",
                title="Included Paper",
                status=PaperStatus.INCLUDED,
                source=PaperSource.SEED
            ),
            Paper(
                id="p2",
                title="Excluded Paper",
                status=PaperStatus.EXCLUDED,
                source=PaperSource.SEED
            ),
            Paper(
                id="p3",
                title="Pending Paper",
                status=PaperStatus.PENDING,
                source=PaperSource.SEED
            ),
        ]
        result = exporter.export(papers, only_included=True)
        
        assert "Included Paper" in result
        assert "Excluded Paper" not in result
        assert "Pending Paper" not in result

    def test_export_all_papers(self, exporter):
        """Test exporting all papers regardless of status."""
        papers = [
            Paper(
                id="p1",
                title="Included Paper",
                status=PaperStatus.INCLUDED,
                source=PaperSource.SEED
            ),
            Paper(
                id="p2",
                title="Excluded Paper",
                status=PaperStatus.EXCLUDED,
                source=PaperSource.SEED
            ),
        ]
        result = exporter.export(papers, only_included=False)
        
        assert "Included Paper" in result
        assert "Excluded Paper" in result

    def test_export_includes_doi(self, exporter, paper_for_export):
        """Test that DOI is included in export."""
        result = exporter.export([paper_for_export], only_included=True)
        assert "doi = {10.1234/test.doi}" in result

    def test_export_includes_arxiv(self, exporter, paper_for_export):
        """Test that arXiv ID is included in export."""
        result = exporter.export([paper_for_export], only_included=True)
        assert "eprint = {2301.00001}" in result
        assert "archivePrefix = {arXiv}" in result

    def test_export_includes_pmid(self, exporter, paper_for_export):
        """Test that PMID is included in export."""
        result = exporter.export([paper_for_export], only_included=True)
        assert "pmid = {12345678}" in result

    def test_export_includes_venue_fields(self, exporter, paper_for_export):
        """Test that venue fields are included."""
        result = exporter.export([paper_for_export], only_included=True)
        assert "journal = {Nature Machine Intelligence}" in result
        assert "volume = {5}" in result
        assert "number = {3}" in result
        assert "pages = {100-120}" in result

    def test_export_conference_paper(self, exporter):
        """Test exporting a conference paper."""
        paper = Paper(
            id="conf-paper",
            title="Conference Paper Title",
            venue=Venue(name="NeurIPS 2023", type="conference"),
            status=PaperStatus.INCLUDED,
            source=PaperSource.SEED
        )
        result = exporter.export([paper], only_included=True)
        
        assert "@inproceedings{" in result
        assert "booktitle = {NeurIPS 2023}" in result

    def test_export_abstract_cleaned(self, exporter):
        """Test that abstract is cleaned for BibTeX."""
        paper = Paper(
            id="test",
            title="Test Paper",
            abstract="Abstract with {braces} and\nnewlines",
            status=PaperStatus.INCLUDED,
            source=PaperSource.SEED
        )
        result = exporter.export([paper], only_included=True)
        
        # Braces and newlines should be removed/replaced
        assert "{braces}" not in result
        assert "\\n" not in result


class TestBibTeXCiteKey:
    """Tests for BibTeX citation key generation."""

    @pytest.fixture
    def exporter(self):
        """Create a BibTeX exporter instance."""
        return BibTeXExporter()

    def test_cite_key_format(self, exporter):
        """Test that citation key follows expected format."""
        paper = Paper(
            id="test-id",
            title="The Study of Machine Learning",
            authors=[Author(name="John Smith")],
            year=2023,
            status=PaperStatus.INCLUDED,
            source=PaperSource.SEED
        )
        cite_key = exporter._generate_cite_key(paper)
        
        # Should be SmithYearFirstWord format
        assert "Smith" in cite_key
        assert "2023" in cite_key

    def test_cite_key_skips_common_words(self, exporter):
        """Test that citation key skips common words in title."""
        paper = Paper(
            id="test-id",
            title="The A An On Study of Machine Learning",
            authors=[Author(name="John Doe")],
            year=2023,
            status=PaperStatus.INCLUDED,
            source=PaperSource.SEED
        )
        cite_key = exporter._generate_cite_key(paper)
        
        # Should skip "The", "A", "An", "On" and use "Study"
        assert "Study" in cite_key

    def test_cite_key_no_author(self, exporter):
        """Test citation key when no author is present."""
        paper = Paper(
            id="test-id-12345678",
            title="Study of Something",
            year=2023,
            status=PaperStatus.INCLUDED,
            source=PaperSource.SEED
        )
        cite_key = exporter._generate_cite_key(paper)
        
        # Should still generate a key
        assert len(cite_key) > 0

    def test_cite_key_no_year(self, exporter):
        """Test citation key when no year is present."""
        paper = Paper(
            id="test-id",
            title="Study of Something",
            authors=[Author(name="John Doe")],
            status=PaperStatus.INCLUDED,
            source=PaperSource.SEED
        )
        cite_key = exporter._generate_cite_key(paper)
        
        assert "Doe" in cite_key

    def test_cite_key_fallback_to_id(self, exporter):
        """Test citation key falls back to paper ID."""
        paper = Paper(
            id="abcd1234-5678-9012",
            title="",  # Empty title
            status=PaperStatus.INCLUDED,
            source=PaperSource.SEED
        )
        cite_key = exporter._generate_cite_key(paper)
        
        # Should use fallback format
        assert "paper" in cite_key.lower()


class TestBibTeXEntryType:
    """Tests for BibTeX entry type determination."""

    @pytest.fixture
    def exporter(self):
        """Create a BibTeX exporter instance."""
        return BibTeXExporter()

    def test_entry_type_journal(self, exporter):
        """Test article entry type for journal papers."""
        paper = Paper(
            id="test",
            title="Test",
            venue=Venue(type="journal"),
            source=PaperSource.SEED
        )
        entry_type = exporter._determine_entry_type(paper)
        assert entry_type == "article"

    def test_entry_type_conference(self, exporter):
        """Test inproceedings entry type for conference papers."""
        paper = Paper(
            id="test",
            title="Test",
            venue=Venue(type="conference"),
            source=PaperSource.SEED
        )
        entry_type = exporter._determine_entry_type(paper)
        assert entry_type == "inproceedings"

    def test_entry_type_workshop(self, exporter):
        """Test inproceedings entry type for workshop papers."""
        paper = Paper(
            id="test",
            title="Test",
            venue=Venue(type="workshop"),
            source=PaperSource.SEED
        )
        entry_type = exporter._determine_entry_type(paper)
        assert entry_type == "inproceedings"

    def test_entry_type_preprint(self, exporter):
        """Test misc entry type for preprints."""
        paper = Paper(
            id="test",
            title="Test",
            venue=Venue(type="preprint"),
            source=PaperSource.SEED
        )
        entry_type = exporter._determine_entry_type(paper)
        assert entry_type == "misc"

    def test_entry_type_arxiv(self, exporter):
        """Test misc entry type for arXiv papers."""
        paper = Paper(
            id="test",
            title="Test",
            venue=Venue(type="arxiv"),
            source=PaperSource.SEED
        )
        entry_type = exporter._determine_entry_type(paper)
        assert entry_type == "misc"

    def test_entry_type_thesis(self, exporter):
        """Test phdthesis entry type for theses."""
        paper = Paper(
            id="test",
            title="Test",
            venue=Venue(type="thesis"),
            source=PaperSource.SEED
        )
        entry_type = exporter._determine_entry_type(paper)
        assert entry_type == "phdthesis"

    def test_entry_type_default(self, exporter):
        """Test default article entry type."""
        paper = Paper(
            id="test",
            title="Test",
            source=PaperSource.SEED
        )
        entry_type = exporter._determine_entry_type(paper)
        assert entry_type == "article"

    def test_entry_type_unknown_venue_type(self, exporter):
        """Test default for unknown venue type."""
        paper = Paper(
            id="test",
            title="Test",
            venue=Venue(type="unknown"),
            source=PaperSource.SEED
        )
        entry_type = exporter._determine_entry_type(paper)
        assert entry_type == "article"
