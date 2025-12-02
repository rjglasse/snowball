"""Tests for API aggregator."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from snowball.apis.aggregator import APIAggregator
from snowball.models import Paper, PaperSource, Author


class TestAPIAggregator:
    """Tests for APIAggregator class."""

    @pytest.fixture
    def mock_paper(self):
        """Create a mock paper for testing."""
        return Paper(
            id="test-id",
            doi="10.1234/test",
            title="Test Paper",
            semantic_scholar_id="s2-123",
            openalex_id="oa-123",
            source=PaperSource.SEED
        )

    def test_init_default_apis(self):
        """Test that all APIs are initialized by default."""
        with patch('snowball.apis.aggregator.SemanticScholarClient'), \
             patch('snowball.apis.aggregator.CrossRefClient'), \
             patch('snowball.apis.aggregator.OpenAlexClient'), \
             patch('snowball.apis.aggregator.ArXivClient'):
            
            aggregator = APIAggregator()
            
            assert "semantic_scholar" in aggregator.clients
            assert "crossref" in aggregator.clients
            assert "openalex" in aggregator.clients
            assert "arxiv" in aggregator.clients

    def test_init_selected_apis(self):
        """Test initializing with only selected APIs."""
        with patch('snowball.apis.aggregator.SemanticScholarClient'):
            aggregator = APIAggregator(use_apis=["semantic_scholar"])
            
            assert "semantic_scholar" in aggregator.clients
            assert "crossref" not in aggregator.clients
            assert "openalex" not in aggregator.clients

    @patch('snowball.apis.aggregator.SemanticScholarClient')
    @patch('snowball.apis.aggregator.CrossRefClient')
    @patch('snowball.apis.aggregator.OpenAlexClient')
    @patch('snowball.apis.aggregator.ArXivClient')
    def test_search_by_doi_tries_apis_in_order(
        self, mock_arxiv, mock_openalex, mock_crossref, mock_s2
    ):
        """Test that search_by_doi tries APIs in priority order."""
        # Set up mocks
        mock_s2_instance = Mock()
        mock_s2_instance.search_by_doi.return_value = None
        mock_s2.return_value = mock_s2_instance
        
        mock_oa_instance = Mock()
        found_paper = Paper(id="found", title="Found", source=PaperSource.SEED)
        mock_oa_instance.search_by_doi.return_value = found_paper
        mock_oa_instance.enrich_metadata.return_value = found_paper
        mock_openalex.return_value = mock_oa_instance
        
        mock_cr_instance = Mock()
        mock_cr_instance.enrich_metadata.return_value = found_paper
        mock_crossref.return_value = mock_cr_instance
        
        mock_arxiv.return_value = Mock()
        
        aggregator = APIAggregator()
        result = aggregator.search_by_doi("10.1234/test")
        
        # Should have tried S2 first, then OpenAlex
        mock_s2_instance.search_by_doi.assert_called_once()
        mock_oa_instance.search_by_doi.assert_called_once()

    @patch('snowball.apis.aggregator.SemanticScholarClient')
    @patch('snowball.apis.aggregator.CrossRefClient')
    @patch('snowball.apis.aggregator.OpenAlexClient')
    @patch('snowball.apis.aggregator.ArXivClient')
    def test_search_by_doi_returns_first_match(
        self, mock_arxiv, mock_openalex, mock_crossref, mock_s2
    ):
        """Test that search returns first successful match."""
        found_paper = Paper(id="found", title="Found", source=PaperSource.SEED)
        
        mock_s2_instance = Mock()
        mock_s2_instance.search_by_doi.return_value = found_paper
        mock_s2_instance.enrich_metadata.return_value = found_paper
        mock_s2.return_value = mock_s2_instance
        
        mock_oa_instance = Mock()
        mock_oa_instance.enrich_metadata.return_value = found_paper
        mock_openalex.return_value = mock_oa_instance
        
        mock_cr_instance = Mock()
        mock_cr_instance.enrich_metadata.return_value = found_paper
        mock_crossref.return_value = mock_cr_instance
        
        mock_arxiv_instance = Mock()
        mock_arxiv_instance.enrich_metadata.return_value = found_paper
        mock_arxiv.return_value = mock_arxiv_instance
        
        aggregator = APIAggregator()
        result = aggregator.search_by_doi("10.1234/test")
        
        assert result is not None
        assert result.title == "Found"

    @patch('snowball.apis.aggregator.SemanticScholarClient')
    @patch('snowball.apis.aggregator.CrossRefClient')
    @patch('snowball.apis.aggregator.OpenAlexClient')
    @patch('snowball.apis.aggregator.ArXivClient')
    def test_search_by_doi_not_found(
        self, mock_arxiv, mock_openalex, mock_crossref, mock_s2
    ):
        """Test search returns None when paper not found in any API."""
        for mock_class in [mock_s2, mock_openalex, mock_crossref, mock_arxiv]:
            mock_instance = Mock()
            mock_instance.search_by_doi.return_value = None
            mock_class.return_value = mock_instance
        
        aggregator = APIAggregator()
        result = aggregator.search_by_doi("10.9999/nonexistent")
        
        assert result is None

    @patch('snowball.apis.aggregator.SemanticScholarClient')
    @patch('snowball.apis.aggregator.CrossRefClient')
    @patch('snowball.apis.aggregator.OpenAlexClient')
    @patch('snowball.apis.aggregator.ArXivClient')
    def test_get_references_uses_semantic_scholar(
        self, mock_arxiv, mock_openalex, mock_crossref, mock_s2
    ):
        """Test that get_references prefers Semantic Scholar."""
        ref_paper = Paper(id="ref", title="Reference", source=PaperSource.BACKWARD)
        
        mock_s2_instance = Mock()
        mock_s2_instance.get_references.return_value = [ref_paper]
        mock_s2.return_value = mock_s2_instance
        
        for mock_class in [mock_openalex, mock_crossref, mock_arxiv]:
            mock_class.return_value = Mock()
        
        aggregator = APIAggregator()
        paper = Paper(
            id="test",
            title="Test",
            semantic_scholar_id="s2-123",
            source=PaperSource.SEED
        )
        
        refs = aggregator.get_references(paper)
        
        assert len(refs) == 1
        mock_s2_instance.get_references.assert_called_once()

    @patch('snowball.apis.aggregator.SemanticScholarClient')
    @patch('snowball.apis.aggregator.CrossRefClient')
    @patch('snowball.apis.aggregator.OpenAlexClient')
    @patch('snowball.apis.aggregator.ArXivClient')
    def test_get_citations_uses_semantic_scholar(
        self, mock_arxiv, mock_openalex, mock_crossref, mock_s2
    ):
        """Test that get_citations prefers Semantic Scholar."""
        cit_paper = Paper(id="cit", title="Citation", source=PaperSource.FORWARD)
        
        mock_s2_instance = Mock()
        mock_s2_instance.get_citations.return_value = [cit_paper]
        mock_s2.return_value = mock_s2_instance
        
        for mock_class in [mock_openalex, mock_crossref, mock_arxiv]:
            mock_class.return_value = Mock()
        
        aggregator = APIAggregator()
        paper = Paper(
            id="test",
            title="Test",
            semantic_scholar_id="s2-123",
            source=PaperSource.SEED
        )
        
        cits = aggregator.get_citations(paper)
        
        assert len(cits) == 1
        mock_s2_instance.get_citations.assert_called_once()

    @patch('snowball.apis.aggregator.SemanticScholarClient')
    @patch('snowball.apis.aggregator.CrossRefClient')
    @patch('snowball.apis.aggregator.OpenAlexClient')
    @patch('snowball.apis.aggregator.ArXivClient')
    def test_enrich_metadata_calls_all_apis(
        self, mock_arxiv, mock_openalex, mock_crossref, mock_s2
    ):
        """Test that enrich_metadata calls all APIs."""
        paper = Paper(id="test", title="Test", source=PaperSource.SEED)
        
        mock_s2_instance = Mock()
        mock_s2_instance.enrich_metadata.return_value = paper
        mock_s2.return_value = mock_s2_instance
        
        mock_oa_instance = Mock()
        mock_oa_instance.enrich_metadata.return_value = paper
        mock_openalex.return_value = mock_oa_instance
        
        mock_cr_instance = Mock()
        mock_cr_instance.enrich_metadata.return_value = paper
        mock_crossref.return_value = mock_cr_instance
        
        mock_arxiv_instance = Mock()
        mock_arxiv_instance.enrich_metadata.return_value = paper
        mock_arxiv.return_value = mock_arxiv_instance
        
        aggregator = APIAggregator()
        aggregator.enrich_metadata(paper)
        
        # All APIs should be called for enrichment
        mock_s2_instance.enrich_metadata.assert_called_once()
        mock_oa_instance.enrich_metadata.assert_called_once()
        mock_cr_instance.enrich_metadata.assert_called_once()
        mock_arxiv_instance.enrich_metadata.assert_called_once()

    @patch('snowball.apis.aggregator.SemanticScholarClient')
    @patch('snowball.apis.aggregator.CrossRefClient')
    @patch('snowball.apis.aggregator.OpenAlexClient')
    @patch('snowball.apis.aggregator.ArXivClient')
    def test_identify_paper_by_doi(
        self, mock_arxiv, mock_openalex, mock_crossref, mock_s2
    ):
        """Test identifying a paper by DOI."""
        found_paper = Paper(
            id="found",
            title="Found",
            doi="10.1234/test",
            semantic_scholar_id="s2-found",
            openalex_id="oa-found",
            source=PaperSource.SEED
        )
        
        mock_s2_instance = Mock()
        mock_s2_instance.search_by_doi.return_value = found_paper
        mock_s2_instance.enrich_metadata.return_value = found_paper
        mock_s2.return_value = mock_s2_instance
        
        mock_oa_instance = Mock()
        mock_oa_instance.enrich_metadata.return_value = found_paper
        mock_openalex.return_value = mock_oa_instance
        
        mock_cr_instance = Mock()
        mock_cr_instance.enrich_metadata.return_value = found_paper
        mock_crossref.return_value = mock_cr_instance
        
        mock_arxiv_instance = Mock()
        mock_arxiv_instance.enrich_metadata.return_value = found_paper
        mock_arxiv.return_value = mock_arxiv_instance
        
        aggregator = APIAggregator()
        paper = Paper(
            id="test",
            title="Test",
            doi="10.1234/test",
            source=PaperSource.SEED
        )
        
        result = aggregator.identify_paper(paper)
        
        assert result.semantic_scholar_id == "s2-found"

    @patch('snowball.apis.aggregator.SemanticScholarClient')
    @patch('snowball.apis.aggregator.CrossRefClient')
    @patch('snowball.apis.aggregator.OpenAlexClient')
    @patch('snowball.apis.aggregator.ArXivClient')
    def test_identify_paper_by_title(
        self, mock_arxiv, mock_openalex, mock_crossref, mock_s2
    ):
        """Test identifying a paper by title when no DOI."""
        found_paper = Paper(
            id="found",
            title="Found Paper",
            doi="10.1234/found",
            semantic_scholar_id="s2-found",
            source=PaperSource.SEED
        )
        
        mock_s2_instance = Mock()
        mock_s2_instance.search_by_title.return_value = found_paper
        mock_s2_instance.enrich_metadata.return_value = found_paper
        mock_s2.return_value = mock_s2_instance
        
        for mock_class in [mock_openalex, mock_crossref, mock_arxiv]:
            mock_instance = Mock()
            mock_instance.enrich_metadata.return_value = found_paper
            mock_class.return_value = mock_instance
        
        aggregator = APIAggregator()
        paper = Paper(
            id="test",
            title="Found Paper",
            source=PaperSource.SEED
        )
        
        result = aggregator.identify_paper(paper)
        
        assert result.doi == "10.1234/found"
