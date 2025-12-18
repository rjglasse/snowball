"""Tests for TikZ export functionality."""

import pytest

from snowball.exporters.tikz import TikZExporter
from snowball.models import Paper, Author, PaperStatus, PaperSource


class TestTikZExporter:
    """Tests for TikZExporter class."""

    @pytest.fixture
    def exporter(self):
        """Create a TikZ exporter instance."""
        return TikZExporter()

    @pytest.fixture
    def paper_for_export(self):
        """Create a paper with all fields for export testing."""
        return Paper(
            id="test-id-1",
            title="A Comprehensive Study of Machine Learning",
            authors=[
                Author(name="John Doe"),
                Author(name="Jane Smith"),
            ],
            year=2023,
            status=PaperStatus.INCLUDED,
            source=PaperSource.SEED,
            snowball_iteration=0,
            citation_count=42,
            source_paper_ids=[],
        )

    def test_export_empty_list(self, exporter):
        """Test exporting an empty list of papers."""
        result = exporter.export([], only_included=False)
        assert result == ""

    def test_export_single_paper(self, exporter, paper_for_export):
        """Test exporting a single paper."""
        result = exporter.export([paper_for_export], only_included=True)

        assert r"\begin{tikzpicture}" in result
        assert r"\end{tikzpicture}" in result
        assert "node[paper]" in result
        assert "A Comprehensive Study of Machine Learning" in result
        assert "Doe et al." in result
        assert "2023" in result

    def test_export_filters_by_included(self, exporter):
        """Test that only_included=True filters out non-included papers."""
        papers = [
            Paper(
                id="p1",
                title="Included Paper",
                status=PaperStatus.INCLUDED,
                source=PaperSource.SEED,
                snowball_iteration=0,
                source_paper_ids=[],
            ),
            Paper(
                id="p2",
                title="Excluded Paper",
                status=PaperStatus.EXCLUDED,
                source=PaperSource.BACKWARD,
                snowball_iteration=1,
                source_paper_ids=[],
            ),
            Paper(
                id="p3",
                title="Pending Paper",
                status=PaperStatus.PENDING,
                source=PaperSource.FORWARD,
                snowball_iteration=1,
                source_paper_ids=[],
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
                source=PaperSource.SEED,
                snowball_iteration=0,
                source_paper_ids=[],
            ),
            Paper(
                id="p2",
                title="Excluded Paper",
                status=PaperStatus.EXCLUDED,
                source=PaperSource.BACKWARD,
                snowball_iteration=1,
                source_paper_ids=[],
            ),
        ]
        result = exporter.export(papers, only_included=False)

        assert "Included Paper" in result
        assert "Excluded Paper" in result

    def test_export_with_edges(self, exporter):
        """Test exporting papers with citation edges."""
        papers = [
            Paper(
                id="p1",
                title="Seed Paper",
                status=PaperStatus.INCLUDED,
                source=PaperSource.SEED,
                snowball_iteration=0,
                source_paper_ids=[],
            ),
            Paper(
                id="p2",
                title="Cited Paper",
                status=PaperStatus.INCLUDED,
                source=PaperSource.BACKWARD,
                snowball_iteration=1,
                source_paper_ids=["p1"],
            ),
        ]
        result = exporter.export(papers, only_included=True)

        assert r"\draw[citation]" in result
        assert "node_p1" in result
        assert "node_p2" in result

    def test_export_standalone(self, exporter, paper_for_export):
        """Test exporting as standalone LaTeX document."""
        result = exporter.export([paper_for_export], only_included=True, standalone=True)

        assert r"\documentclass[tikz,border=10pt]{standalone}" in result
        assert r"\usepackage{tikz}" in result
        assert r"\begin{document}" in result
        assert r"\end{document}" in result
        assert r"\begin{tikzpicture}" in result

    def test_export_non_standalone(self, exporter, paper_for_export):
        """Test exporting as non-standalone TikZ code."""
        result = exporter.export([paper_for_export], only_included=True, standalone=False)

        assert r"\documentclass" not in result
        assert r"\begin{document}" not in result
        assert r"\begin{tikzpicture}" in result

    def test_export_positions_by_iteration(self, exporter):
        """Test that papers are positioned by iteration."""
        papers = [
            Paper(
                id="p0",
                title="Seed Paper",
                status=PaperStatus.INCLUDED,
                source=PaperSource.SEED,
                snowball_iteration=0,
                source_paper_ids=[],
            ),
            Paper(
                id="p1",
                title="First Iteration Paper",
                status=PaperStatus.INCLUDED,
                source=PaperSource.BACKWARD,
                snowball_iteration=1,
                source_paper_ids=["p0"],
            ),
            Paper(
                id="p2",
                title="Second Iteration Paper",
                status=PaperStatus.INCLUDED,
                source=PaperSource.BACKWARD,
                snowball_iteration=2,
                source_paper_ids=["p1"],
            ),
        ]
        result = exporter.export(papers, only_included=True)

        # Check that nodes are positioned at different x coordinates
        assert "at (0.0cm," in result  # iteration 0
        assert "at (6.0cm," in result  # iteration 1
        assert "at (12.0cm," in result  # iteration 2

    def test_escape_latex_special_chars(self, exporter):
        """Test that special LaTeX characters are escaped."""
        paper = Paper(
            id="special-chars",
            title="Test & Special $ Characters % # _ { }",
            status=PaperStatus.INCLUDED,
            source=PaperSource.SEED,
            snowball_iteration=0,
            source_paper_ids=[],
        )
        result = exporter.export([paper], only_included=True)

        # Special chars should be escaped
        assert r"\&" in result
        assert r"\$" in result
        assert r"\%" in result
        assert r"\#" in result
        assert r"\_" in result

    def test_truncate_long_title(self, exporter):
        """Test that long titles are truncated."""
        long_title = "This is a very long paper title that exceeds the maximum length and should be truncated properly"
        paper = Paper(
            id="long-title",
            title=long_title,
            status=PaperStatus.INCLUDED,
            source=PaperSource.SEED,
            snowball_iteration=0,
            source_paper_ids=[],
        )
        result = exporter.export([paper], only_included=True)

        # Should be truncated with ellipsis
        assert "..." in result

    def test_sanitize_node_ids(self, exporter):
        """Test that node IDs are sanitized for TikZ."""
        paper = Paper(
            id="test@paper#123$weird%id",
            title="Test Paper",
            status=PaperStatus.INCLUDED,
            source=PaperSource.SEED,
            snowball_iteration=0,
            source_paper_ids=[],
        )
        result = exporter.export([paper], only_included=True)

        # Special chars in IDs should be replaced
        assert "node_test_paper_123_weird_id" in result or "node_test" in result

    def test_single_author_name(self, exporter):
        """Test formatting with a single author."""
        paper = Paper(
            id="single-author",
            title="Test Paper",
            authors=[Author(name="John Doe")],
            year=2023,
            status=PaperStatus.INCLUDED,
            source=PaperSource.SEED,
            snowball_iteration=0,
            source_paper_ids=[],
        )
        result = exporter.export([paper], only_included=True)

        # Single author should not have "et al."
        assert "Doe" in result
        assert "et al." not in result

    def test_multiple_authors_name(self, exporter):
        """Test formatting with multiple authors."""
        paper = Paper(
            id="multi-author",
            title="Test Paper",
            authors=[
                Author(name="John Doe"),
                Author(name="Jane Smith"),
                Author(name="Bob Johnson"),
            ],
            year=2023,
            status=PaperStatus.INCLUDED,
            source=PaperSource.SEED,
            snowball_iteration=0,
            source_paper_ids=[],
        )
        result = exporter.export([paper], only_included=True)

        # Multiple authors should have "et al."
        assert "Doe et al." in result

    def test_no_author(self, exporter):
        """Test formatting with no author."""
        paper = Paper(
            id="no-author",
            title="Test Paper",
            year=2023,
            status=PaperStatus.INCLUDED,
            source=PaperSource.SEED,
            snowball_iteration=0,
            source_paper_ids=[],
        )
        result = exporter.export([paper], only_included=True)

        # Should still generate valid TikZ
        assert r"\begin{tikzpicture}" in result
        assert "2023" in result


class TestTikZExporterHelpers:
    """Tests for TikZ exporter helper methods."""

    @pytest.fixture
    def exporter(self):
        """Create a TikZ exporter instance."""
        return TikZExporter()

    def test_truncate_title_short(self, exporter):
        """Test truncating a short title."""
        title = "Short Title"
        result = exporter._truncate_title(title, max_length=60)
        assert result == "Short Title"

    def test_truncate_title_long(self, exporter):
        """Test truncating a long title."""
        title = (
            "This is a very long title that exceeds the maximum length and needs to be truncated"
        )
        result = exporter._truncate_title(title, max_length=60)
        assert len(result) <= 63  # 60 + "..."
        assert result.endswith("...")

    def test_escape_latex_ampersand(self, exporter):
        """Test escaping ampersand."""
        result = exporter._escape_latex("Text & More")
        assert result == r"Text \& More"

    def test_escape_latex_percent(self, exporter):
        """Test escaping percent."""
        result = exporter._escape_latex("50% Done")
        assert result == r"50\% Done"

    def test_escape_latex_dollar(self, exporter):
        """Test escaping dollar sign."""
        result = exporter._escape_latex("$100")
        assert result == r"\$100"

    def test_sanitize_id_alphanumeric(self, exporter):
        """Test sanitizing alphanumeric IDs."""
        result = exporter._sanitize_id("test123-abc")
        assert result == "node_test123-abc"

    def test_sanitize_id_special_chars(self, exporter):
        """Test sanitizing IDs with special characters."""
        result = exporter._sanitize_id("test@#$%paper")
        assert result.startswith("node_")
        assert "@" not in result
        assert "#" not in result
        assert "$" not in result
        assert "%" not in result

    def test_truncate_title_no_spaces(self, exporter):
        """Test truncating a title with no spaces (single very long word)."""
        title = "A" * 100
        result = exporter._truncate_title(title, max_length=60)
        assert len(result) == 63  # 60 + "..."
        assert result.endswith("...")

    def test_author_name_empty(self, exporter):
        """Test formatting with empty author name."""
        paper = Paper(
            id="empty-author",
            title="Test Paper",
            authors=[Author(name="")],
            year=2023,
            status=PaperStatus.INCLUDED,
            source=PaperSource.SEED,
            snowball_iteration=0,
            source_paper_ids=[],
        )
        result = exporter.export([paper], only_included=True)

        # Should still generate valid TikZ even with empty author
        assert r"\begin{tikzpicture}" in result
        assert "2023" in result
