"""Tests for paper filtering functionality."""

import pytest

from snowball.filters.filter_engine import FilterEngine
from snowball.models import Paper, PaperSource, FilterCriteria, Venue


class TestFilterEngine:
    """Tests for FilterEngine class."""

    @pytest.fixture
    def filter_engine(self):
        """Create a filter engine instance."""
        return FilterEngine()

    @pytest.fixture
    def papers_with_years(self):
        """Create papers with different years."""
        return [
            Paper(id="p1", title="Paper 2019", year=2019, source=PaperSource.SEED),
            Paper(id="p2", title="Paper 2020", year=2020, source=PaperSource.SEED),
            Paper(id="p3", title="Paper 2021", year=2021, source=PaperSource.SEED),
            Paper(id="p4", title="Paper 2022", year=2022, source=PaperSource.SEED),
            Paper(id="p5", title="Paper None Year", year=None, source=PaperSource.SEED),
        ]

    @pytest.fixture
    def papers_with_citations(self):
        """Create papers with different citation counts."""
        return [
            Paper(id="p1", title="Low Citations", citation_count=5, source=PaperSource.SEED),
            Paper(id="p2", title="Medium Citations", citation_count=50, source=PaperSource.SEED),
            Paper(id="p3", title="High Citations", citation_count=500, source=PaperSource.SEED),
            Paper(id="p4", title="No Citations", citation_count=None, source=PaperSource.SEED),
        ]

    def test_filter_empty_criteria(self, filter_engine, papers_with_years):
        """Test that empty criteria returns all papers."""
        criteria = FilterCriteria()
        result = filter_engine.apply_filters(papers_with_years, criteria)
        assert len(result) == len(papers_with_years)

    def test_filter_min_year(self, filter_engine, papers_with_years):
        """Test filtering by minimum year."""
        criteria = FilterCriteria(min_year=2021)
        result = filter_engine.apply_filters(papers_with_years, criteria)
        
        # Should include 2021, 2022, and None year (None passes filter)
        years = [p.year for p in result if p.year]
        assert all(y >= 2021 for y in years)
        assert any(p.year is None for p in result)

    def test_filter_max_year(self, filter_engine, papers_with_years):
        """Test filtering by maximum year."""
        criteria = FilterCriteria(max_year=2020)
        result = filter_engine.apply_filters(papers_with_years, criteria)
        
        years = [p.year for p in result if p.year]
        assert all(y <= 2020 for y in years)

    def test_filter_year_range(self, filter_engine, papers_with_years):
        """Test filtering by year range."""
        criteria = FilterCriteria(min_year=2020, max_year=2021)
        result = filter_engine.apply_filters(papers_with_years, criteria)
        
        years = [p.year for p in result if p.year]
        assert all(2020 <= y <= 2021 for y in years)

    def test_filter_min_citations(self, filter_engine, papers_with_citations):
        """Test filtering by minimum citation count."""
        criteria = FilterCriteria(min_citations=50)
        result = filter_engine.apply_filters(papers_with_citations, criteria)
        
        # Should include Medium (50), High (500), and None (passes filter)
        assert len(result) == 3
        for p in result:
            if p.citation_count is not None:
                assert p.citation_count >= 50

    def test_filter_max_citations(self, filter_engine, papers_with_citations):
        """Test filtering by maximum citation count."""
        criteria = FilterCriteria(max_citations=100)
        result = filter_engine.apply_filters(papers_with_citations, criteria)
        
        for p in result:
            if p.citation_count is not None:
                assert p.citation_count <= 100

    def test_filter_keywords_in_title(self, filter_engine):
        """Test filtering by keywords in title."""
        papers = [
            Paper(id="p1", title="Machine Learning Study", source=PaperSource.SEED),
            Paper(id="p2", title="Deep Learning Methods", source=PaperSource.SEED),
            Paper(id="p3", title="Statistical Analysis", source=PaperSource.SEED),
        ]
        criteria = FilterCriteria(keywords=["machine learning", "deep learning"])
        result = filter_engine.apply_filters(papers, criteria)
        
        assert len(result) == 2
        titles = [p.title for p in result]
        assert "Machine Learning Study" in titles
        assert "Deep Learning Methods" in titles

    def test_filter_keywords_in_abstract(self, filter_engine):
        """Test filtering by keywords in abstract."""
        papers = [
            Paper(
                id="p1",
                title="Paper One",
                abstract="This paper discusses machine learning applications.",
                source=PaperSource.SEED
            ),
            Paper(
                id="p2",
                title="Paper Two",
                abstract="This paper discusses database systems.",
                source=PaperSource.SEED
            ),
        ]
        criteria = FilterCriteria(keywords=["machine learning"])
        result = filter_engine.apply_filters(papers, criteria)
        
        assert len(result) == 1
        assert result[0].id == "p1"

    def test_filter_keywords_case_insensitive(self, filter_engine):
        """Test that keyword filtering is case-insensitive."""
        papers = [
            Paper(id="p1", title="MACHINE LEARNING Study", source=PaperSource.SEED),
        ]
        criteria = FilterCriteria(keywords=["machine learning"])
        result = filter_engine.apply_filters(papers, criteria)
        
        assert len(result) == 1

    def test_filter_excluded_keywords(self, filter_engine):
        """Test filtering by excluded keywords."""
        papers = [
            Paper(id="p1", title="Machine Learning Survey", source=PaperSource.SEED),
            Paper(id="p2", title="Machine Learning Methods", source=PaperSource.SEED),
            Paper(id="p3", title="Deep Learning Review", source=PaperSource.SEED),
        ]
        criteria = FilterCriteria(excluded_keywords=["survey", "review"])
        result = filter_engine.apply_filters(papers, criteria)
        
        assert len(result) == 1
        assert result[0].id == "p2"

    def test_filter_venue_types(self, filter_engine):
        """Test filtering by venue type."""
        papers = [
            Paper(
                id="p1",
                title="Journal Paper",
                venue=Venue(name="Nature", type="journal"),
                source=PaperSource.SEED
            ),
            Paper(
                id="p2",
                title="Conference Paper",
                venue=Venue(name="NeurIPS", type="conference"),
                source=PaperSource.SEED
            ),
            Paper(
                id="p3",
                title="Workshop Paper",
                venue=Venue(name="Workshop", type="workshop"),
                source=PaperSource.SEED
            ),
            Paper(
                id="p4",
                title="No Venue Paper",
                source=PaperSource.SEED
            ),
        ]
        criteria = FilterCriteria(venue_types=["journal", "conference"])
        result = filter_engine.apply_filters(papers, criteria)
        
        # Should include journal, conference, and no venue (passes filter)
        assert len(result) == 3

    def test_filter_influential_citations(self, filter_engine):
        """Test filtering by influential citation count."""
        papers = [
            Paper(
                id="p1",
                title="Low Influence",
                influential_citation_count=2,
                source=PaperSource.SEED
            ),
            Paper(
                id="p2",
                title="High Influence",
                influential_citation_count=20,
                source=PaperSource.SEED
            ),
            Paper(
                id="p3",
                title="No Influence Data",
                influential_citation_count=None,
                source=PaperSource.SEED
            ),
        ]
        criteria = FilterCriteria(min_influential_citations=10)
        result = filter_engine.apply_filters(papers, criteria)
        
        # Should include High Influence and None (passes filter)
        assert len(result) == 2

    def test_filter_combined_criteria(self, filter_engine):
        """Test filtering with multiple criteria combined."""
        papers = [
            Paper(
                id="p1",
                title="ML Paper 2022",
                year=2022,
                citation_count=100,
                source=PaperSource.SEED
            ),
            Paper(
                id="p2",
                title="ML Paper 2019",
                year=2019,
                citation_count=100,
                source=PaperSource.SEED
            ),
            Paper(
                id="p3",
                title="Stats Paper 2022",
                year=2022,
                citation_count=5,
                source=PaperSource.SEED
            ),
        ]
        criteria = FilterCriteria(
            min_year=2020,
            min_citations=50
        )
        result = filter_engine.apply_filters(papers, criteria)
        
        assert len(result) == 1
        assert result[0].id == "p1"

    def test_filter_empty_paper_list(self, filter_engine):
        """Test filtering an empty list of papers."""
        criteria = FilterCriteria(min_year=2020)
        result = filter_engine.apply_filters([], criteria)
        assert result == []

    def test_filter_papers_without_text(self, filter_engine):
        """Test keyword filtering on papers without title/abstract."""
        papers = [
            Paper(id="p1", title="", source=PaperSource.SEED),
        ]
        # Papers without searchable text should pass keyword filter
        criteria = FilterCriteria(keywords=["machine learning"])
        result = filter_engine.apply_filters(papers, criteria)
        assert len(result) == 1


class TestFilterEngineVenueQuality:
    """Tests for venue quality estimation."""

    @pytest.fixture
    def filter_engine(self):
        """Create a filter engine instance."""
        return FilterEngine()

    def test_estimate_venue_quality_high(self, filter_engine):
        """Test high quality estimation for highly cited paper."""
        paper = Paper(
            id="p1",
            title="Highly Cited",
            citation_count=150,
            venue=Venue(name="Nature"),
            source=PaperSource.SEED
        )
        quality = filter_engine.estimate_venue_quality(paper)
        assert quality == "high"

    def test_estimate_venue_quality_medium(self, filter_engine):
        """Test medium quality estimation."""
        paper = Paper(
            id="p1",
            title="Medium Cited",
            citation_count=50,
            venue=Venue(name="Some Journal"),
            source=PaperSource.SEED
        )
        quality = filter_engine.estimate_venue_quality(paper)
        assert quality == "medium"

    def test_estimate_venue_quality_low(self, filter_engine):
        """Test low quality estimation."""
        paper = Paper(
            id="p1",
            title="Low Cited",
            citation_count=5,
            venue=Venue(name="Small Journal"),
            source=PaperSource.SEED
        )
        quality = filter_engine.estimate_venue_quality(paper)
        assert quality == "low"

    def test_estimate_venue_quality_unknown_no_venue(self, filter_engine):
        """Test unknown quality for paper without venue."""
        paper = Paper(
            id="p1",
            title="No Venue Paper",
            citation_count=100,
            source=PaperSource.SEED
        )
        quality = filter_engine.estimate_venue_quality(paper)
        assert quality == "unknown"

    def test_estimate_venue_quality_unknown_no_citations(self, filter_engine):
        """Test unknown quality for paper without citation count."""
        paper = Paper(
            id="p1",
            title="No Citations Data",
            citation_count=None,
            venue=Venue(name="Some Journal"),
            source=PaperSource.SEED
        )
        quality = filter_engine.estimate_venue_quality(paper)
        assert quality == "unknown"
