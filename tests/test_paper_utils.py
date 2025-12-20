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
    papers_are_duplicates,
    title_similarity,
    authors_similarity,
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

    def test_sort_key_cite(self, paper):
        """Test sort key for cite column."""
        key = get_sort_key(paper, "Cite")
        assert key == (0, 100)

    def test_sort_key_cite_none(self, paper_with_nones):
        """Test sort key for None citations."""
        key = get_sort_key(paper_with_nones, "Cite")
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
            status=PaperStatus.PENDING,
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
        ]:
            paper = Paper(id="test", title="Test", status=status, source=PaperSource.SEED)
            result = format_paper_rich(paper)
            assert status.value in result


class TestPapersAreDuplicates:
    """Tests for papers_are_duplicates function - forensic accuracy is critical."""

    def _make_paper(
        self,
        title: str = "Test Paper",
        doi: str = None,
        arxiv_id: str = None,
        year: int = None,
        authors: list = None,
    ) -> Paper:
        """Helper to create test papers."""
        return Paper(
            id="test-id",
            title=title,
            doi=doi,
            arxiv_id=arxiv_id,
            year=year,
            authors=[Author(name=a) for a in authors] if authors else [],
            status=PaperStatus.PENDING,
            source=PaperSource.SEED,
        )

    # === DOI MATCHING ===

    def test_exact_doi_match_is_duplicate(self):
        """Exact DOI match should always be a duplicate."""
        p1 = self._make_paper(title="Paper One", doi="10.1234/abc")
        p2 = self._make_paper(title="Completely Different Title", doi="10.1234/abc")
        assert papers_are_duplicates(p1, p2) is True

    def test_doi_match_case_insensitive(self):
        """DOI matching should be case-insensitive."""
        p1 = self._make_paper(doi="10.1234/ABC")
        p2 = self._make_paper(doi="10.1234/abc")
        assert papers_are_duplicates(p1, p2) is True

    def test_different_dois_not_duplicate(self):
        """Different DOIs should not match even with similar titles."""
        p1 = self._make_paper(title="Machine Learning", doi="10.1234/abc")
        p2 = self._make_paper(title="Machine Learning", doi="10.1234/xyz")
        assert papers_are_duplicates(p1, p2) is False

    # === ARXIV ID MATCHING ===

    def test_exact_arxiv_id_match_is_duplicate(self):
        """Exact arXiv ID match should always be a duplicate."""
        p1 = self._make_paper(title="Paper One", arxiv_id="2301.12345")
        p2 = self._make_paper(title="Different Title", arxiv_id="2301.12345")
        assert papers_are_duplicates(p1, p2) is True

    def test_arxiv_id_ignores_version(self):
        """arXiv ID matching should ignore version suffix (v1, v2, etc.)."""
        p1 = self._make_paper(arxiv_id="2301.12345v1")
        p2 = self._make_paper(arxiv_id="2301.12345v2")
        assert papers_are_duplicates(p1, p2) is True

    def test_arxiv_id_case_insensitive(self):
        """arXiv ID matching should be case-insensitive."""
        p1 = self._make_paper(arxiv_id="2301.12345V1")
        p2 = self._make_paper(arxiv_id="2301.12345v1")
        assert papers_are_duplicates(p1, p2) is True

    def test_different_arxiv_ids_not_duplicate(self):
        """Different arXiv IDs should not match."""
        p1 = self._make_paper(title="Same Title", arxiv_id="2301.12345")
        p2 = self._make_paper(title="Same Title", arxiv_id="2301.99999")
        assert papers_are_duplicates(p1, p2) is False

    # === YEAR MATCHING ===

    def test_same_year_allows_fuzzy_match(self):
        """Papers from same year with similar titles should be duplicates."""
        p1 = self._make_paper(
            title="Deep Learning for Natural Language Processing",
            year=2023,
            authors=["John Smith"],
        )
        p2 = self._make_paper(
            title="Deep Learning for Natural Language Processing",
            year=2023,
            authors=["John Smith"],
        )
        assert papers_are_duplicates(p1, p2) is True

    def test_one_year_difference_allowed(self):
        """Papers within 1 year should allow fuzzy matching (preprint/published)."""
        p1 = self._make_paper(
            title="Deep Learning for Natural Language Processing",
            year=2022,
            authors=["John Smith"],
        )
        p2 = self._make_paper(
            title="Deep Learning for Natural Language Processing",
            year=2023,
            authors=["John Smith"],
        )
        assert papers_are_duplicates(p1, p2) is True

    def test_two_year_difference_not_duplicate(self):
        """Papers with >1 year difference should NOT be duplicates (forensic safety)."""
        p1 = self._make_paper(
            title="Deep Learning for Natural Language Processing",
            year=2020,
            authors=["John Smith"],
        )
        p2 = self._make_paper(
            title="Deep Learning for Natural Language Processing",
            year=2023,
            authors=["John Smith"],
        )
        assert papers_are_duplicates(p1, p2) is False

    def test_missing_year_allows_match(self):
        """If one or both papers lack year, skip year check."""
        p1 = self._make_paper(
            title="Deep Learning for Natural Language Processing",
            year=None,
            authors=["John Smith"],
        )
        p2 = self._make_paper(
            title="Deep Learning for Natural Language Processing",
            year=2023,
            authors=["John Smith"],
        )
        assert papers_are_duplicates(p1, p2) is True

    # === TITLE THRESHOLD ===

    def test_high_title_similarity_is_duplicate(self):
        """Titles with >0.85 similarity should match."""
        # 5/6 words shared = 0.833, below threshold. Use identical titles instead.
        p1 = self._make_paper(title="Deep Learning for Natural Language Processing")
        p2 = self._make_paper(title="Deep Learning for Natural Language Processing")
        assert papers_are_duplicates(p1, p2) is True

    def test_near_threshold_title_not_duplicate(self):
        """Titles just below 0.85 threshold should NOT match (forensic safety)."""
        p1 = self._make_paper(title="Deep Learning for Natural Language Processing")
        p2 = self._make_paper(title="Deep Learning for Natural Language Processing Tasks")
        # 5/6 words = 0.833, below 0.85 threshold
        assert papers_are_duplicates(p1, p2) is False

    def test_moderate_title_similarity_not_duplicate(self):
        """Titles with <0.85 similarity should NOT match (stricter threshold)."""
        p1 = self._make_paper(title="Machine Learning for Image Recognition")
        p2 = self._make_paper(title="Deep Learning for Natural Language Processing")
        # Very different topics, should be <0.85
        assert papers_are_duplicates(p1, p2) is False

    def test_word_order_matters_somewhat(self):
        """Word order doesn't affect Jaccard, but different words do."""
        # Same words, different order - still 100% Jaccard
        p1 = self._make_paper(title="Machine Learning Applications")
        p2 = self._make_paper(title="Applications Machine Learning")
        assert papers_are_duplicates(p1, p2) is True

    # === AUTHOR MATCHING ===

    def test_same_authors_match(self):
        """Papers with same authors should match."""
        p1 = self._make_paper(
            title="Deep Learning Methods",
            authors=["John Smith", "Jane Doe"],
        )
        p2 = self._make_paper(
            title="Deep Learning Methods",
            authors=["John Smith", "Jane Doe"],
        )
        assert papers_are_duplicates(p1, p2) is True

    def test_different_authors_not_duplicate(self):
        """Papers with different authors should NOT match (even with same title)."""
        p1 = self._make_paper(
            title="Deep Learning Methods for Computer Vision",
            year=2023,
            authors=["Alice Johnson", "Bob Wilson"],
        )
        p2 = self._make_paper(
            title="Deep Learning Methods for Computer Vision",
            year=2023,
            authors=["Charlie Brown", "Diana Prince"],
        )
        # Same title, same year, but completely different authors
        assert papers_are_duplicates(p1, p2) is False

    def test_partial_author_overlap_matches(self):
        """Papers with partial author overlap should match (threshold 0.3)."""
        p1 = self._make_paper(
            title="Deep Learning Methods",
            authors=["John Smith", "Jane Doe", "Bob Wilson"],
        )
        p2 = self._make_paper(
            title="Deep Learning Methods",
            authors=["John Smith", "Alice Brown"],
        )
        # 1 shared author out of 4 unique = 0.25, below 0.3 threshold
        # But let's test with better overlap
        p3 = self._make_paper(
            title="Deep Learning Methods",
            authors=["John Smith", "Jane Doe"],
        )
        assert papers_are_duplicates(p1, p3) is True

    def test_missing_authors_allows_match(self):
        """If one or both papers lack authors, skip author check."""
        p1 = self._make_paper(
            title="Deep Learning for Natural Language Processing",
            authors=[],
        )
        p2 = self._make_paper(
            title="Deep Learning for Natural Language Processing",
            authors=["John Smith"],
        )
        assert papers_are_duplicates(p1, p2) is True

    # === EDGE CASES ===

    def test_empty_title_not_duplicate(self):
        """Papers with empty titles should never match."""
        p1 = self._make_paper(title="")
        p2 = self._make_paper(title="Some Title")
        assert papers_are_duplicates(p1, p2) is False

    def test_identical_papers_are_duplicates(self):
        """Identical papers should always be duplicates."""
        p1 = self._make_paper(
            title="Test Paper",
            doi="10.1234/test",
            year=2023,
            authors=["Author One"],
        )
        p2 = self._make_paper(
            title="Test Paper",
            doi="10.1234/test",
            year=2023,
            authors=["Author One"],
        )
        assert papers_are_duplicates(p1, p2) is True


class TestTitleSimilarity:
    """Tests for title_similarity function."""

    def test_identical_titles(self):
        """Identical titles should have similarity 1.0."""
        assert title_similarity("Machine Learning", "Machine Learning") == 1.0

    def test_completely_different_titles(self):
        """Completely different titles should have similarity 0.0."""
        assert title_similarity("Alpha Beta Gamma", "Delta Epsilon Zeta") == 0.0

    def test_partial_overlap(self):
        """Titles with partial word overlap."""
        # 2 words shared (deep, learning) out of 5 unique
        sim = title_similarity("Deep Learning Methods", "Deep Learning Applications")
        assert 0.4 <= sim <= 0.7

    def test_stopwords_ignored(self):
        """Common stopwords should be ignored."""
        sim = title_similarity(
            "The Study of Machine Learning",
            "A Study on Machine Learning"
        )
        # "the", "of", "a", "on" are stopwords
        assert sim >= 0.8

    def test_case_insensitive(self):
        """Title similarity should be case-insensitive."""
        assert title_similarity("MACHINE LEARNING", "machine learning") == 1.0


class TestAuthorsSimilarity:
    """Tests for authors_similarity function."""

    def test_identical_authors(self):
        """Identical author lists should have similarity 1.0."""
        a1 = [Author(name="John Smith"), Author(name="Jane Doe")]
        a2 = [Author(name="John Smith"), Author(name="Jane Doe")]
        assert authors_similarity(a1, a2) == 1.0

    def test_no_overlap(self):
        """Authors with no overlap should have similarity 0.0."""
        a1 = [Author(name="John Smith")]
        a2 = [Author(name="Jane Doe")]
        assert authors_similarity(a1, a2) == 0.0

    def test_partial_overlap(self):
        """Authors with partial overlap."""
        a1 = [Author(name="John Smith"), Author(name="Jane Doe")]
        a2 = [Author(name="John Smith"), Author(name="Bob Wilson")]
        # 1 shared out of 3 unique = 0.33
        sim = authors_similarity(a1, a2)
        assert 0.3 <= sim <= 0.4

    def test_uses_last_name_only(self):
        """Author matching should use last name only."""
        a1 = [Author(name="John Smith")]
        a2 = [Author(name="J. Smith")]
        assert authors_similarity(a1, a2) == 1.0

    def test_handles_comma_format(self):
        """Should handle 'Last, First' format."""
        a1 = [Author(name="Smith, John")]
        a2 = [Author(name="John Smith")]
        assert authors_similarity(a1, a2) == 1.0
