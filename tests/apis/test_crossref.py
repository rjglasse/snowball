"""Tests for CrossRef API client."""

import pytest
from unittest.mock import Mock, patch

from snowball.apis.crossref import CrossRefClient
from snowball.apis.base import RateLimitError, APINotFoundError
from snowball.models import Paper, PaperSource


class TestCrossRefClient:
    """Tests for CrossRefClient class."""

    @pytest.fixture
    def client(self):
        """Create a CrossRef client instance."""
        return CrossRefClient(rate_limit_delay=0)

    @pytest.fixture
    def client_with_email(self):
        """Create a CrossRef client with email for polite pool."""
        return CrossRefClient(email="test@example.com", rate_limit_delay=0)

    @pytest.fixture
    def mock_work_response(self):
        """Create a mock CrossRef API response for a work."""
        return {
            "message": {
                "DOI": "10.1234/test.doi",
                "title": ["A Comprehensive Study of Machine Learning"],
                "author": [
                    {"given": "John", "family": "Doe"},
                    {"given": "Jane", "family": "Smith"}
                ],
                "published": {"date-parts": [[2023, 5, 15]]},
                "container-title": ["Nature Machine Intelligence"],
                "type": "journal-article",
                "volume": "5",
                "issue": "3",
                "page": "100-120",
                "abstract": "This paper presents a study on machine learning.",
                "is-referenced-by-count": 150
            }
        }

    def test_init_without_email(self, client):
        """Test client initialization without email."""
        assert client.rate_limit_delay == 0
        assert client.client is not None

    def test_init_with_email(self, client_with_email):
        """Test client initialization with email sets polite pool header."""
        # Client should have email in User-Agent
        assert "mailto:test@example.com" in client_with_email.client.headers.get("User-Agent", "")

    @patch.object(CrossRefClient, '_make_request')
    def test_search_by_doi(self, mock_request, client, mock_work_response):
        """Test searching for a paper by DOI."""
        mock_request.return_value = mock_work_response

        paper = client.search_by_doi("10.1234/test.doi")

        assert paper is not None
        assert paper.title == "A Comprehensive Study of Machine Learning"
        assert paper.doi == "10.1234/test.doi"
        assert paper.year == 2023
        assert paper.citation_count == 150

    @patch.object(CrossRefClient, '_make_request')
    def test_search_by_doi_not_found(self, mock_request, client):
        """Test searching for a DOI that doesn't exist."""
        mock_request.side_effect = APINotFoundError("Not found")

        paper = client.search_by_doi("10.9999/nonexistent")

        assert paper is None

    @patch.object(CrossRefClient, '_make_request')
    def test_search_by_title(self, mock_request, client, mock_work_response):
        """Test searching for a paper by title."""
        mock_request.return_value = {
            "message": {
                "items": [mock_work_response["message"]]
            }
        }

        paper = client.search_by_title("Machine Learning Study")

        assert paper is not None
        assert paper.title == "A Comprehensive Study of Machine Learning"

    @patch.object(CrossRefClient, '_make_request')
    def test_search_by_title_no_results(self, mock_request, client):
        """Test searching by title with no results."""
        mock_request.return_value = {"message": {"items": []}}

        paper = client.search_by_title("Nonexistent Paper")

        assert paper is None

    def test_get_references_returns_empty(self, client):
        """Test that get_references returns empty list."""
        result = client.get_references("10.1234/test")
        assert result == []

    def test_get_citations_returns_empty(self, client):
        """Test that get_citations returns empty list."""
        result = client.get_citations("10.1234/test")
        assert result == []


class TestCrossRefParsePaper:
    """Tests for parsing CrossRef API responses."""

    @pytest.fixture
    def client(self):
        """Create a CrossRef client instance."""
        return CrossRefClient(rate_limit_delay=0)

    def test_parse_paper_extracts_all_fields(self, client):
        """Test that _parse_paper extracts all fields correctly."""
        data = {
            "DOI": "10.1234/test.doi",
            "title": ["Test Paper Title"],
            "author": [
                {"given": "John", "family": "Doe"},
                {"given": "Jane", "family": "Smith"}
            ],
            "published": {"date-parts": [[2023, 5, 15]]},
            "container-title": ["Nature"],
            "type": "journal-article",
            "volume": "5",
            "issue": "3",
            "page": "100-120",
            "abstract": "Test abstract text.",
            "is-referenced-by-count": 100
        }

        paper = client._parse_paper(data)

        assert paper.doi == "10.1234/test.doi"
        assert paper.title == "Test Paper Title"
        assert paper.year == 2023
        assert paper.abstract == "Test abstract text."
        assert paper.citation_count == 100
        assert len(paper.authors) == 2
        assert paper.authors[0].name == "John Doe"
        assert paper.venue is not None
        assert paper.venue.name == "Nature"
        assert paper.venue.volume == "5"
        assert paper.venue.issue == "3"
        assert paper.venue.pages == "100-120"

    def test_parse_paper_handles_missing_fields(self, client):
        """Test that _parse_paper handles missing optional fields."""
        data = {
            "title": ["Minimal Paper"]
        }

        paper = client._parse_paper(data)

        assert paper.title == "Minimal Paper"
        assert paper.doi is None
        assert paper.year is None
        assert paper.authors == []
        assert paper.venue is None

    def test_parse_paper_handles_empty_title_list(self, client):
        """Test that _parse_paper handles empty title list."""
        data = {
            "title": []
        }

        paper = client._parse_paper(data)

        assert paper.title == "Unknown Title"

    def test_parse_paper_with_custom_source(self, client):
        """Test parsing paper with custom source."""
        data = {"title": ["Test Paper"]}

        paper = client._parse_paper(data, source=PaperSource.FORWARD)

        assert paper.source == PaperSource.FORWARD

    def test_parse_paper_extracts_authors_with_missing_parts(self, client):
        """Test parsing authors with missing given or family names."""
        data = {
            "title": ["Test"],
            "author": [
                {"family": "Doe"},  # No given name
                {"given": "Jane"},  # No family name
                {"given": "Bob", "family": "Johnson"}
            ]
        }

        paper = client._parse_paper(data)

        assert len(paper.authors) == 3
        assert paper.authors[0].name == "Doe"
        assert paper.authors[1].name == "Jane"
        assert paper.authors[2].name == "Bob Johnson"


class TestCrossRefEnrichMetadata:
    """Tests for CrossRef metadata enrichment."""

    @pytest.fixture
    def client(self):
        """Create a CrossRef client instance."""
        return CrossRefClient(rate_limit_delay=0)

    @patch.object(CrossRefClient, 'search_by_doi')
    def test_enrich_metadata_with_doi(self, mock_search, client):
        """Test enriching paper with DOI."""
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
            source=PaperSource.SEED
        )
        mock_search.return_value = enriched_paper

        result = client.enrich_metadata(existing_paper)

        assert result.abstract == "Enriched abstract"
        assert result.year == 2023
        assert result.citation_count == 100
        mock_search.assert_called_once_with("10.1234/test")

    @patch.object(CrossRefClient, 'search_by_doi')
    @patch.object(CrossRefClient, 'search_by_title')
    def test_enrich_metadata_falls_back_to_title(self, mock_title, mock_doi, client):
        """Test enriching paper by title when no DOI."""
        existing_paper = Paper(
            id="test",
            title="Test Paper",
            source=PaperSource.SEED
        )

        enriched_paper = Paper(
            id="enriched",
            title="Test Paper",
            doi="10.1234/found",
            abstract="Found abstract",
            source=PaperSource.SEED
        )
        mock_doi.return_value = None
        mock_title.return_value = enriched_paper

        result = client.enrich_metadata(existing_paper)

        assert result.doi == "10.1234/found"
        assert result.abstract == "Found abstract"
        mock_title.assert_called_once_with("Test Paper")

    @patch.object(CrossRefClient, 'search_by_doi')
    def test_enrich_metadata_no_result(self, mock_search, client):
        """Test enriching paper when no result found."""
        existing_paper = Paper(
            id="test",
            title="Unknown Paper",
            doi="10.9999/unknown",
            source=PaperSource.SEED
        )
        mock_search.return_value = None

        result = client.enrich_metadata(existing_paper)

        # Should return paper unchanged
        assert result.title == "Unknown Paper"
        assert result.abstract is None

    @patch.object(CrossRefClient, 'search_by_doi')
    def test_enrich_metadata_merges_raw_data(self, mock_search, client):
        """Test that enrichment merges raw_data."""
        existing_paper = Paper(
            id="test",
            title="Test Paper",
            doi="10.1234/test",
            source=PaperSource.SEED,
            raw_data={"existing": "data"}
        )

        enriched_paper = Paper(
            id="enriched",
            title="Test Paper",
            source=PaperSource.SEED,
            raw_data={"crossref": {"new": "data"}}
        )
        mock_search.return_value = enriched_paper

        result = client.enrich_metadata(existing_paper)

        assert "existing" in result.raw_data
        assert "crossref" in result.raw_data


class TestCrossRefMakeRequest:
    """Tests for CrossRef API request handling."""

    @pytest.fixture
    def client(self):
        """Create a CrossRef client instance."""
        return CrossRefClient(rate_limit_delay=0)

    @patch('httpx.Client.get')
    def test_make_request_success(self, mock_get, client):
        """Test successful API request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": {"DOI": "10.1234/test"}}
        mock_get.return_value = mock_response

        result = client._make_request("works/10.1234/test")

        assert result == {"message": {"DOI": "10.1234/test"}}

    @patch('httpx.Client.get')
    def test_make_request_rate_limit(self, mock_get, client):
        """Test API request with rate limit error."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_get.return_value = mock_response

        with pytest.raises(RateLimitError):
            client._make_request("works/10.1234/test")

    @patch('httpx.Client.get')
    def test_make_request_not_found(self, mock_get, client):
        """Test API request with 404 error."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        with pytest.raises(APINotFoundError):
            client._make_request("works/10.9999/nonexistent")

    @patch('httpx.Client.get')
    def test_make_request_other_error(self, mock_get, client):
        """Test API request with other error status code."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        result = client._make_request("works/10.1234/test")

        assert result == {}

    @patch('httpx.Client.get')
    def test_make_request_timeout(self, mock_get, client):
        """Test API request timeout handling."""
        import httpx
        mock_get.side_effect = httpx.TimeoutException("Timeout")

        result = client._make_request("works/10.1234/test")

        assert result == {}
