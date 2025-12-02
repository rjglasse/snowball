"""Tests for paper utility functions."""

import pytest

from snowball.paper_utils import (
    get_status_value,
    get_source_value,
    filter_papers,
    sort_papers,
    get_sort_key,
    format_authors,
    truncate_title,
    paper_to_dict,
    format_paper_text,
    format_paper_rich,
    STATUS_ORDER,
    SOURCE_ORDER,
    MAX_AUTHORS_DISPLAY,
    MAX_TITLE_LENGTH,
)
from snowball.models import Paper, Author, Venue, PaperStatus, PaperSource


class TestGetStatusValue:
    """Tests for get_status_value function."""

    def test_with_enum(self):
        """Test getting value from PaperStatus enum."""
        assert get_status_value(PaperStatus.PENDING) == "pending"
        assert get_status_value(PaperStatus.INCLUDED) == "included"
        assert get_status_value(PaperStatus.EXCLUDED) == "excluded"
        assert get_status_value(PaperStatus.MAYBE) == "maybe"

    def test_with_string(self):
        """Test passing string directly."""
        assert get_status_value("pending") == "pending"
        assert get_status_value("included") == "included"


class TestGetSourceValue:
    """Tests for get_source_value function."""

    def test_with_enum(self):
        """Test getting value from PaperSource enum."""
        assert get_source_value(PaperSource.SEED) == "seed"
        assert get_source_value(PaperSource.BACKWARD) == "backward"
        assert get_source_value(PaperSource.FORWARD) == "forward"

    def test_with_string(self):
        """Test passing string directly."""
        assert get_source_value("seed") == "seed"
        assert get_source_value("forward") == "forward"


class TestFilterPapers:
    """Tests for filter_papers function."""

    @pytest.fixture
    def mixed_papers(self):
        """Create a list of papers with different statuses, iterations, and sources."""
        return [
            Paper(
                id="p1",
                title="Paper 1",
                status=PaperStatus.INCLUDED,
                source=PaperSource.SEED,
                snowball_iteration=0,
            ),
            Paper(
                id="p2",
                title="Paper 2",
                status=PaperStatus.PENDING,
                source=PaperSource.BACKWARD,
                snowball_iteration=1,
            ),
            Paper(
                id="p3",
                title="Paper 3",
                status=PaperStatus.EXCLUDED,
                source=PaperSource.FORWARD,
                snowball_iteration=1,
            ),
            Paper(
                id="p4",
                title="Paper 4",
                status=PaperStatus.INCLUDED,
                source=PaperSource.BACKWARD,
                snowball_iteration=2,
            ),
        ]

    def test_filter_by_status(self, mixed_papers):
        """Test filtering by status."""
        result = filter_papers(mixed_papers, status="included")
        assert len(result) == 2
        assert all(p.status == PaperStatus.INCLUDED for p in result)

    def test_filter_by_iteration(self, mixed_papers):
        """Test filtering by iteration."""
        result = filter_papers(mixed_papers, iteration=1)
        assert len(result) == 2
        assert all(p.snowball_iteration == 1 for p in result)

    def test_filter_by_source(self, mixed_papers):
        """Test filtering by source."""
        result = filter_papers(mixed_papers, source="backward")
        assert len(result) == 2
        assert all(get_source_value(p.source) == "backward" for p in result)

    def test_filter_combined(self, mixed_papers):
        """Test filtering with multiple criteria."""
        result = filter_papers(mixed_papers, status="included", source="backward")
        assert len(result) == 1
        assert result[0].id == "p4"

    def test_filter_no_criteria(self, mixed_papers):
        """Test filtering with no criteria returns all papers."""
        result = filter_papers(mixed_papers)
        assert len(result) == len(mixed_papers)


class TestSortPapers:
    """Tests for sort_papers function."""

    @pytest.fixture
    def papers_for_sorting(self):
        """Create papers with sortable fields."""
        return [
            Paper(
                id="p1",
                title="Alpha Paper",
                year=2022,
                citation_count=50,
                status=PaperStatus.PENDING,
                source=PaperSource.SEED,
            ),
            Paper(
                id="p2",
                title="Beta Paper",
                year=2020,
                citation_count=100,
                status=PaperStatus.INCLUDED,
                source=PaperSource.SEED,
            ),
            Paper(
                id="p3",
                title="Gamma Paper",
                year=None,
                citation_count=None,
                status=PaperStatus.EXCLUDED,
                source=PaperSource.SEED,
            ),
        ]

    def test_sort_by_citations(self, papers_for_sorting):
        """Test sorting by citations descending."""
        result = sort_papers(papers_for_sorting.copy(), sort_by="citations")
        # Should be: 100, 50, None (at end)
        assert result[0].citation_count == 100
        assert result[1].citation_count == 50
        assert result[2].citation_count is None

    def test_sort_by_year(self, papers_for_sorting):
        """Test sorting by year descending."""
        result = sort_papers(papers_for_sorting.copy(), sort_by="year")
        # Should be: 2022, 2020, None (at end)
        assert result[0].year == 2022
        assert result[1].year == 2020
        assert result[2].year is None

    def test_sort_by_title(self, papers_for_sorting):
        """Test sorting by title ascending."""
        result = sort_papers(papers_for_sorting.copy(), sort_by="title", ascending=True)
        assert result[0].title == "Alpha Paper"
        assert result[1].title == "Beta Paper"
        assert result[2].title == "Gamma Paper"

    def test_sort_by_title_descending(self, papers_for_sorting):
        """Test sorting by title descending."""
        result = sort_papers(papers_for_sorting.copy(), sort_by="title", ascending=False)
        assert result[0].title == "Gamma Paper"
        assert result[2].title == "Alpha Paper"

    def test_sort_by_status(self, papers_for_sorting):
        """Test sorting by status."""
        result = sort_papers(papers_for_sorting.copy(), sort_by="status")
        # Status order: pending=0, included=1, excluded=2
        assert get_status_value(result[0].status) == "pending"
        assert get_status_value(result[1].status) == "included"
        assert get_status_value(result[2].status) == "excluded"


class TestGetSortKey:
    """Tests for get_sort_key function."""

    @pytest.fixture
    def paper(self):
        """Create a test paper."""
        return Paper(
            id="test",
            title="Test Paper Title",
            year=2023,
            citation_count=100,
            status=PaperStatus.INCLUDED,
            source=PaperSource.BACKWARD,
            snowball_iteration=1,
        )

    @pytest.fixture
    def paper_with_nones(self):
        """Create a test paper with None values for optional fields."""
        return Paper(
            id="test-none",
            title="",  # Empty title since title is required
            year=None,
            citation_count=None,
            status=PaperStatus.PENDING,
            source=PaperSource.SEED,
        )

    def test_sort_key_status(self, paper):
        """Test sort key for status column."""
        key = get_sort_key(paper, "Status")
        assert key == (0, STATUS_ORDER["included"])

    def test_sort_key_title(self, paper):
        """Test sort key for title column."""
        key = get_sort_key(paper, "Title")
        assert key == (0, "test paper title")

    def test_sort_key_title_none(self, paper_with_nones):
        """Test sort key for empty title.

        The source code uses 'zzz' as a fallback for falsy titles to ensure
        they sort to the end alphabetically.
        """
        key = get_sort_key(paper_with_nones, "Title")
        # Empty title treated as falsy and maps to "zzz" for sorting to end
        assert key == (0, "zzz")

    def test_sort_key_year(self, paper):
        """Test sort key for year column."""
        key = get_sort_key(paper, "Year")
        assert key == (0, 2023)

    def test_sort_key_year_none(self, paper_with_nones):
        """Test sort key for None year."""
        key = get_sort_key(paper_with_nones, "Year")
        assert key == (1, 0)  # None goes to end

    def test_sort_key_citations(self, paper):
        """Test sort key for citations column."""
        key = get_sort_key(paper, "Citations")
        assert key == (0, 100)

    def test_sort_key_citations_none(self, paper_with_nones):
        """Test sort key for None citations."""
        key = get_sort_key(paper_with_nones, "Citations")
        assert key == (1, 0)  # None goes to end

    def test_sort_key_source(self, paper):
        """Test sort key for source column."""
        key = get_sort_key(paper, "Source")
        assert key == (0, SOURCE_ORDER["backward"])

    def test_sort_key_iteration(self, paper):
        """Test sort key for iteration column."""
        key = get_sort_key(paper, "Iter")
        assert key == (0, 1)

    def test_sort_key_unknown_column(self, paper):
        """Test sort key for unknown column uses fallback."""
        key = get_sort_key(paper, "UnknownColumn")
        # Fallback: (0, (iteration, status))
        assert key[0] == 0
        assert key[1] == (1, "included")


class TestFormatAuthors:
    """Tests for format_authors function."""

    def test_empty_authors(self):
        """Test formatting empty author list."""
        result = format_authors([])
        assert result == ""

    def test_single_author(self):
        """Test formatting single author."""
        authors = [Author(name="John Doe")]
        result = format_authors(authors)
        assert result == "John Doe"

    def test_multiple_authors(self):
        """Test formatting multiple authors."""
        authors = [
            Author(name="John Doe"),
            Author(name="Jane Smith"),
            Author(name="Bob Johnson"),
        ]
        result = format_authors(authors)
        assert result == "John Doe, Jane Smith, Bob Johnson"

    def test_truncate_many_authors(self):
        """Test truncating when more than max authors."""
        authors = [Author(name=f"Author {i}") for i in range(15)]
        result = format_authors(authors, max_display=10)
        assert "(+5 more)" in result

    def test_custom_max_display(self):
        """Test with custom max_display."""
        authors = [Author(name=f"Author {i}") for i in range(5)]
        result = format_authors(authors, max_display=3)
        assert "(+2 more)" in result


class TestTruncateTitle:
    """Tests for truncate_title function."""

    def test_short_title(self):
        """Test that short titles are not truncated."""
        title = "Short Title"
        result = truncate_title(title)
        assert result == title
        assert "..." not in result

    def test_long_title(self):
        """Test that long titles are truncated."""
        title = "A" * 100
        result = truncate_title(title)
        assert len(result) == MAX_TITLE_LENGTH + 3  # Plus "..."
        assert result.endswith("...")

    def test_custom_max_length(self):
        """Test with custom max length."""
        title = "A Very Long Title That Should Be Truncated"
        result = truncate_title(title, max_length=20)
        assert len(result) == 23  # 20 + "..."
        assert result.endswith("...")


class TestPaperToDict:
    """Tests for paper_to_dict function."""

    @pytest.fixture
    def full_paper(self):
        """Create a paper with all fields."""
        return Paper(
            id="test-id",
            title="Test Paper",
            doi="10.1234/test",
            arxiv_id="2301.00001",
            year=2023,
            citation_count=100,
            influential_citation_count=10,
            status=PaperStatus.INCLUDED,
            source=PaperSource.SEED,
            snowball_iteration=0,
            authors=[Author(name="John Doe")],
            abstract="Test abstract",
            venue=Venue(name="Nature"),
            notes="Test notes",
            tags=["ml", "ai"],
        )

    def test_basic_fields(self, full_paper):
        """Test that basic fields are included."""
        result = paper_to_dict(full_paper)
        assert result["id"] == "test-id"
        assert result["title"] == "Test Paper"
        assert result["year"] == 2023
        assert result["status"] == "included"
        assert result["source"] == "seed"
        assert result["iteration"] == 0
        assert result["citations"] == 100
        assert result["doi"] == "10.1234/test"
        assert result["arxiv_id"] == "2301.00001"

    def test_without_abstract(self, full_paper):
        """Test that abstract is not included by default."""
        result = paper_to_dict(full_paper, include_abstract=False)
        assert "abstract" not in result
        assert "authors" not in result
        assert "notes" not in result

    def test_with_abstract(self, full_paper):
        """Test including abstract and additional fields."""
        result = paper_to_dict(full_paper, include_abstract=True)
        assert result["abstract"] == "Test abstract"
        assert result["authors"] == ["John Doe"]
        assert result["influential_citations"] == 10
        assert result["venue"] == "Nature"
        assert result["notes"] == "Test notes"
        assert result["tags"] == ["ml", "ai"]

    def test_with_none_venue(self):
        """Test with no venue."""
        paper = Paper(id="test", title="Test", source=PaperSource.SEED)
        result = paper_to_dict(paper, include_abstract=True)
        assert result["venue"] is None


class TestFormatPaperText:
    """Tests for format_paper_text function."""

    @pytest.fixture
    def paper(self):
        """Create a test paper."""
        return Paper(
            id="test-id",
            title="Test Paper Title",
            doi="10.1234/test",
            arxiv_id="2301.00001",
            year=2023,
            citation_count=100,
            influential_citation_count=10,
            status=PaperStatus.INCLUDED,
            source=PaperSource.SEED,
            snowball_iteration=0,
            authors=[Author(name="John Doe")],
            abstract="This is a test abstract.",
            venue=Venue(name="Nature"),
            notes="Test notes",
            tags=["ml", "ai"],
        )

    def test_format_includes_title(self, paper):
        """Test that title is included."""
        result = format_paper_text(paper)
        assert "Test Paper Title" in result

    def test_format_includes_identifiers(self, paper):
        """Test that identifiers are included."""
        result = format_paper_text(paper)
        assert "test-id" in result
        assert "10.1234/test" in result
        assert "2301.00001" in result

    def test_format_includes_status(self, paper):
        """Test that status is included."""
        result = format_paper_text(paper)
        assert "included" in result

    def test_format_includes_year(self, paper):
        """Test that year is included."""
        result = format_paper_text(paper)
        assert "2023" in result

    def test_format_includes_authors(self, paper):
        """Test that authors are included."""
        result = format_paper_text(paper)
        assert "John Doe" in result

    def test_format_includes_venue(self, paper):
        """Test that venue is included."""
        result = format_paper_text(paper)
        assert "Nature" in result

    def test_format_includes_abstract(self, paper):
        """Test that abstract is included."""
        result = format_paper_text(paper)
        assert "This is a test abstract." in result

    def test_format_includes_notes(self, paper):
        """Test that notes are included."""
        result = format_paper_text(paper)
        assert "Test notes" in result

    def test_format_includes_tags(self, paper):
        """Test that tags are included."""
        result = format_paper_text(paper)
        assert "ml" in result
        assert "ai" in result

    def test_format_includes_citations(self, paper):
        """Test that citations are included."""
        result = format_paper_text(paper)
        assert "100" in result
        assert "influential: 10" in result


class TestFormatPaperRich:
    """Tests for format_paper_rich function."""

    @pytest.fixture
    def paper(self):
        """Create a test paper."""
        return Paper(
            id="test-id",
            title="Test Paper Title",
            doi="10.1234/test",
            arxiv_id="2301.00001",
            year=2023,
            citation_count=100,
            influential_citation_count=10,
            status=PaperStatus.INCLUDED,
            source=PaperSource.SEED,
            snowball_iteration=0,
            authors=[Author(name="John Doe")],
            abstract="This is a test abstract.",
            venue=Venue(name="Nature"),
            notes="Test notes",
        )

    def test_format_includes_title(self, paper):
        """Test that title is included."""
        result = format_paper_rich(paper)
        assert "Test Paper Title" in result

    def test_format_includes_authors(self, paper):
        """Test that authors are included."""
        result = format_paper_rich(paper)
        assert "John Doe" in result

    def test_format_includes_status_with_color(self, paper):
        """Test that status is included."""
        result = format_paper_rich(paper)
        assert "included" in result

    def test_format_includes_doi(self, paper):
        """Test that DOI is included."""
        result = format_paper_rich(paper)
        assert "DOI: 10.1234/test" in result

    def test_format_includes_arxiv(self, paper):
        """Test that arXiv ID is included."""
        result = format_paper_rich(paper)
        assert "arXiv: 2301.00001" in result

    def test_format_includes_abstract(self, paper):
        """Test that abstract is included."""
        result = format_paper_rich(paper)
        assert "This is a test abstract." in result

    def test_format_includes_notes(self, paper):
        """Test that notes are included."""
        result = format_paper_rich(paper)
        assert "Test notes" in result

    def test_format_paper_without_authors(self):
        """Test formatting paper without authors."""
        paper = Paper(
            id="test",
            title="Test Paper",
            status=PaperStatus.PENDING,
            source=PaperSource.SEED,
        )
        result = format_paper_rich(paper)
        assert "Test Paper" in result
        assert "Authors:" not in result

    def test_format_paper_without_identifiers(self):
        """Test formatting paper without DOI/arXiv."""
        paper = Paper(
            id="test",
            title="Test Paper",
            status=PaperStatus.MAYBE,
            source=PaperSource.FORWARD,
        )
        result = format_paper_rich(paper)
        assert "Test Paper" in result
        assert "DOI:" not in result

    def test_format_different_statuses(self):
        """Test that different statuses get different colors."""
        for status in [
            PaperStatus.PENDING,
            PaperStatus.INCLUDED,
            PaperStatus.EXCLUDED,
            PaperStatus.MAYBE,
        ]:
            paper = Paper(id="test", title="Test", status=status, source=PaperSource.SEED)
            result = format_paper_rich(paper)
            assert status.value in result
