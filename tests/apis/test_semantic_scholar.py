"""Tests for Semantic Scholar API client."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from snowball.apis.semantic_scholar import SemanticScholarClient
from snowball.apis.base import RateLimitError, APINotFoundError
from snowball.models import Paper, PaperSource


class TestSemanticScholarClient:
    """Tests for SemanticScholarClient class."""

    @pytest.fixture
    def client(self):
        """Create a SemanticScholar client instance."""
        return SemanticScholarClient(api_key=None, rate_limit_delay=0)

    @pytest.fixture
    def mock_paper_response(self):
        """Create a mock API response for a paper."""
        return {
            "paperId": "abc123",
            "externalIds": {
                "DOI": "10.1234/test.doi",
                "ArXiv": "2301.00001",
                "PubMed": "12345678"
            },
            "title": "Test Paper Title",
            "abstract": "Test abstract text.",
            "venue": "Nature",
            "year": 2023,
            "authors": [
                {"authorId": "1", "name": "John Doe"},
                {"authorId": "2", "name": "Jane Smith"}
            ],
            "citationCount": 100,
            "influentialCitationCount": 10,
            "publicationTypes": ["JournalArticle"],
            "journal": {"name": "Nature"},
        }

    def test_init_without_api_key(self, client):
        """Test client initialization without API key."""
        assert client.api_key is None

    def test_init_with_api_key(self):
        """Test client initialization with API key."""
        client = SemanticScholarClient(api_key="test-key", rate_limit_delay=0)
        assert client.api_key == "test-key"

    @patch.object(SemanticScholarClient, '_make_request')
    def test_search_by_doi(self, mock_request, client, mock_paper_response):
        """Test searching for a paper by DOI."""
        mock_request.return_value = mock_paper_response
        
        paper = client.search_by_doi("10.1234/test.doi")
        
        assert paper is not None
        assert paper.title == "Test Paper Title"
        assert paper.doi == "10.1234/test.doi"
        assert paper.semantic_scholar_id == "abc123"

    @patch.object(SemanticScholarClient, '_make_request')
    def test_search_by_doi_not_found(self, mock_request, client):
        """Test searching for a DOI that doesn't exist."""
        mock_request.side_effect = APINotFoundError("Not found")
        
        paper = client.search_by_doi("10.9999/nonexistent")
        assert paper is None

    @patch.object(SemanticScholarClient, '_make_request')
    def test_search_by_title(self, mock_request, client, mock_paper_response):
        """Test searching for a paper by title."""
        mock_request.return_value = {"data": [mock_paper_response]}
        
        paper = client.search_by_title("Test Paper Title")
        
        assert paper is not None
        assert paper.title == "Test Paper Title"

    @patch.object(SemanticScholarClient, '_make_request')
    def test_search_by_title_no_results(self, mock_request, client):
        """Test searching by title with no results."""
        mock_request.return_value = {"data": []}
        
        paper = client.search_by_title("Nonexistent Paper")
        assert paper is None

    @patch.object(SemanticScholarClient, '_make_request')
    def test_get_references(self, mock_request, client, mock_paper_response):
        """Test getting references for a paper."""
        mock_request.return_value = {
            "data": [
                {"citedPaper": mock_paper_response}
            ]
        }
        
        references = client.get_references("abc123", limit=10)
        
        assert len(references) == 1
        assert references[0].source == PaperSource.BACKWARD

    @patch.object(SemanticScholarClient, '_make_request')
    def test_get_citations(self, mock_request, client, mock_paper_response):
        """Test getting citations for a paper."""
        mock_request.return_value = {
            "data": [
                {"citingPaper": mock_paper_response}
            ]
        }
        
        citations = client.get_citations("abc123", limit=10)
        
        assert len(citations) == 1
        assert citations[0].source == PaperSource.FORWARD

    @patch.object(SemanticScholarClient, '_make_request')
    def test_get_paper_by_id(self, mock_request, client, mock_paper_response):
        """Test getting a paper by Semantic Scholar ID."""
        mock_request.return_value = mock_paper_response
        
        paper = client.get_paper_by_id("abc123")
        
        assert paper is not None
        assert paper.semantic_scholar_id == "abc123"

    def test_parse_paper_extracts_fields(self, client, mock_paper_response):
        """Test that _parse_paper extracts all fields correctly."""
        paper = client._parse_paper(mock_paper_response)
        
        assert paper.title == "Test Paper Title"
        assert paper.doi == "10.1234/test.doi"
        assert paper.arxiv_id == "2301.00001"
        assert paper.pmid == "12345678"
        assert paper.year == 2023
        assert paper.citation_count == 100
        assert paper.influential_citation_count == 10
        assert len(paper.authors) == 2

    def test_parse_paper_handles_missing_fields(self, client):
        """Test that _parse_paper handles missing optional fields."""
        minimal_response = {
            "paperId": "abc123",
            "title": "Test Paper",
        }
        paper = client._parse_paper(minimal_response)
        
        assert paper.title == "Test Paper"
        assert paper.doi is None
        assert paper.year is None
        assert paper.authors == []

    @patch.object(SemanticScholarClient, 'search_by_doi')
    def test_enrich_metadata(self, mock_search, client):
        """Test enriching paper metadata."""
        existing_paper = Paper(
            id="test",
            title="Original Title",
            doi="10.1234/test",
            source=PaperSource.SEED
        )
        
        enriched_paper = Paper(
            id="enriched",
            title="Enriched Title",
            doi="10.1234/test",
            abstract="Enriched abstract",
            year=2023,
            citation_count=100,
            semantic_scholar_id="abc123",
            source=PaperSource.SEED
        )
        mock_search.return_value = enriched_paper
        
        result = client.enrich_metadata(existing_paper)
        
        # Should have merged data
        assert result.abstract == "Enriched abstract"
        assert result.year == 2023
        assert result.citation_count == 100


class TestSemanticScholarClientRateLimit:
    """Tests for rate limiting behavior."""

    @patch('httpx.Client.get')
    def test_rate_limit_error(self, mock_get):
        """Test handling of rate limit response."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_get.return_value = mock_response
        
        client = SemanticScholarClient(rate_limit_delay=0)
        
        with pytest.raises(RateLimitError):
            client._make_request("test/endpoint")
