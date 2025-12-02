"""Tests for OpenAlex API client."""

import pytest
from unittest.mock import Mock, patch

from snowball.apis.openalex import OpenAlexClient
from snowball.apis.base import RateLimitError, APINotFoundError
from snowball.models import Paper, PaperSource


class TestOpenAlexClient:
    """Tests for OpenAlexClient class."""

    @pytest.fixture
    def client(self):
        """Create an OpenAlex client instance."""
        return OpenAlexClient(rate_limit_delay=0)

    @pytest.fixture
    def client_with_email(self):
        """Create an OpenAlex client with email for polite pool."""
        return OpenAlexClient(email="test@example.com", rate_limit_delay=0)

    @pytest.fixture
    def mock_work_response(self):
        """Create a mock OpenAlex API response for a work."""
        return {
            "id": "https://openalex.org/W1234567890",
            "doi": "https://doi.org/10.1234/test.doi",
            "title": "A Comprehensive Study of Machine Learning",
            "publication_year": 2023,
            "cited_by_count": 150,
            "authorships": [
                {
                    "author": {"display_name": "John Doe"},
                    "institutions": [{"display_name": "MIT"}]
                },
                {
                    "author": {"display_name": "Jane Smith"},
                    "institutions": [{"display_name": "Stanford"}]
                }
            ],
            "primary_location": {
                "source": {
                    "display_name": "Nature Machine Intelligence",
                    "type": "journal"
                }
            },
            "abstract_inverted_index": {
                "This": [0],
                "is": [1],
                "a": [2],
                "test": [3],
                "abstract.": [4]
            },
            "referenced_works": [
                "https://openalex.org/W9999999991",
                "https://openalex.org/W9999999992"
            ]
        }

    def test_init_without_email(self, client):
        """Test client initialization without email."""
        assert client.rate_limit_delay == 0
        assert client.client is not None

    def test_init_with_email(self, client_with_email):
        """Test client initialization with email sets polite pool header."""
        assert "mailto:test@example.com" in client_with_email.client.headers.get("User-Agent", "")

    @patch.object(OpenAlexClient, '_make_request')
    def test_search_by_doi(self, mock_request, client, mock_work_response):
        """Test searching for a paper by DOI."""
        mock_request.return_value = {"results": [mock_work_response]}

        paper = client.search_by_doi("10.1234/test.doi")

        assert paper is not None
        assert paper.title == "A Comprehensive Study of Machine Learning"
        assert paper.doi == "10.1234/test.doi"
        assert paper.year == 2023
        assert paper.citation_count == 150

    @patch.object(OpenAlexClient, '_make_request')
    def test_search_by_doi_not_found(self, mock_request, client):
        """Test searching for a DOI that doesn't exist."""
        mock_request.return_value = {"results": []}

        paper = client.search_by_doi("10.9999/nonexistent")

        assert paper is None

    @patch.object(OpenAlexClient, '_make_request')
    def test_search_by_title(self, mock_request, client, mock_work_response):
        """Test searching for a paper by title."""
        mock_request.return_value = {"results": [mock_work_response]}

        paper = client.search_by_title("Machine Learning Study")

        assert paper is not None
        assert paper.title == "A Comprehensive Study of Machine Learning"

    @patch.object(OpenAlexClient, '_make_request')
    def test_search_by_title_no_results(self, mock_request, client):
        """Test searching by title with no results."""
        mock_request.return_value = {"results": []}

        paper = client.search_by_title("Nonexistent Paper")

        assert paper is None

    @patch.object(OpenAlexClient, '_make_request')
    def test_get_paper_by_id(self, mock_request, client, mock_work_response):
        """Test getting a paper by OpenAlex ID."""
        mock_request.return_value = mock_work_response

        paper = client.get_paper_by_id("W1234567890")

        assert paper is not None
        assert paper.openalex_id == "W1234567890"

    @patch.object(OpenAlexClient, '_make_request')
    def test_get_paper_by_id_adds_prefix(self, mock_request, client, mock_work_response):
        """Test that get_paper_by_id adds W prefix if missing."""
        mock_request.return_value = mock_work_response

        paper = client.get_paper_by_id("1234567890")

        mock_request.assert_called_with("works/W1234567890")


class TestOpenAlexParsePaper:
    """Tests for parsing OpenAlex API responses."""

    @pytest.fixture
    def client(self):
        """Create an OpenAlex client instance."""
        return OpenAlexClient(rate_limit_delay=0)

    def test_parse_paper_extracts_all_fields(self, client):
        """Test that _parse_paper extracts all fields correctly."""
        data = {
            "id": "https://openalex.org/W1234567890",
            "doi": "https://doi.org/10.1234/test.doi",
            "title": "Test Paper Title",
            "publication_year": 2023,
            "cited_by_count": 100,
            "authorships": [
                {
                    "author": {"display_name": "John Doe"},
                    "institutions": [{"display_name": "MIT"}]
                }
            ],
            "primary_location": {
                "source": {
                    "display_name": "Nature",
                    "type": "journal"
                }
            },
            "abstract_inverted_index": {"Test": [0], "abstract": [1]}
        }

        paper = client._parse_paper(data)

        assert paper.openalex_id == "W1234567890"
        assert paper.doi == "10.1234/test.doi"
        assert paper.title == "Test Paper Title"
        assert paper.year == 2023
        assert paper.citation_count == 100
        assert len(paper.authors) == 1
        assert paper.authors[0].name == "John Doe"
        assert paper.authors[0].affiliations == ["MIT"]
        assert paper.venue is not None
        assert paper.venue.name == "Nature"

    def test_parse_paper_handles_missing_fields(self, client):
        """Test that _parse_paper handles missing optional fields."""
        data = {
            "id": "https://openalex.org/W9999",
            "title": "Minimal Paper"
        }

        paper = client._parse_paper(data)

        assert paper.title == "Minimal Paper"
        assert paper.doi is None
        assert paper.year is None
        assert paper.authors == []
        assert paper.venue is None

    def test_parse_paper_with_custom_source(self, client):
        """Test parsing paper with custom source."""
        data = {
            "id": "https://openalex.org/W9999",
            "title": "Test Paper"
        }

        paper = client._parse_paper(data, source=PaperSource.FORWARD)

        assert paper.source == PaperSource.FORWARD

    def test_parse_paper_handles_no_author_institutions(self, client):
        """Test parsing authors without institutions."""
        data = {
            "id": "https://openalex.org/W9999",
            "title": "Test",
            "authorships": [
                {"author": {"display_name": "John Doe"}, "institutions": []}
            ]
        }

        paper = client._parse_paper(data)

        assert len(paper.authors) == 1
        assert paper.authors[0].name == "John Doe"
        assert paper.authors[0].affiliations == []


class TestOpenAlexReconstructAbstract:
    """Tests for abstract reconstruction from inverted index."""

    @pytest.fixture
    def client(self):
        """Create an OpenAlex client instance."""
        return OpenAlexClient(rate_limit_delay=0)

    def test_reconstruct_abstract_simple(self, client):
        """Test reconstructing a simple abstract."""
        inverted_index = {
            "This": [0],
            "is": [1],
            "a": [2],
            "test.": [3]
        }

        result = client._reconstruct_abstract(inverted_index)

        assert result == "This is a test."

    def test_reconstruct_abstract_with_repeated_words(self, client):
        """Test reconstructing abstract with repeated words."""
        inverted_index = {
            "The": [0, 5],
            "cat": [1],
            "and": [2],
            "the": [3],
            "dog.": [4],
            "end.": [6]
        }

        result = client._reconstruct_abstract(inverted_index)

        assert result == "The cat and the dog. The end."

    def test_reconstruct_abstract_empty(self, client):
        """Test reconstructing empty abstract."""
        # Empty inverted index should cause an error
        result = client._reconstruct_abstract({})

        # Should return empty string on error
        assert result == ""


class TestOpenAlexGetReferencesAndCitations:
    """Tests for getting references and citations."""

    @pytest.fixture
    def client(self):
        """Create an OpenAlex client instance."""
        return OpenAlexClient(rate_limit_delay=0)

    @pytest.fixture
    def mock_work_with_refs(self):
        """Create a mock work with referenced works."""
        return {
            "id": "https://openalex.org/W1111",
            "title": "Source Paper",
            "referenced_works": [
                "https://openalex.org/W2222",
                "https://openalex.org/W3333"
            ]
        }

    @pytest.fixture
    def mock_ref_paper(self):
        """Create a mock referenced paper."""
        return {
            "id": "https://openalex.org/W2222",
            "title": "Referenced Paper"
        }

    @patch.object(OpenAlexClient, '_make_request')
    @patch.object(OpenAlexClient, 'get_paper_by_id')
    def test_get_references(self, mock_get_paper, mock_request, client, mock_work_with_refs, mock_ref_paper):
        """Test getting references for a paper."""
        mock_request.return_value = mock_work_with_refs

        ref_paper = Paper(
            id="ref",
            title="Referenced Paper",
            openalex_id="W2222",
            source=PaperSource.SEED
        )
        mock_get_paper.return_value = ref_paper

        references = client.get_references("W1111", limit=10)

        assert len(references) >= 1
        # Verify source is set to BACKWARD for references
        for ref in references:
            assert ref.source == PaperSource.BACKWARD

    @patch.object(OpenAlexClient, '_make_request')
    def test_get_references_no_paper_data(self, mock_request, client):
        """Test getting references when paper not found."""
        mock_request.return_value = {}

        references = client.get_references("W9999")

        assert references == []

    @patch.object(OpenAlexClient, '_make_request')
    def test_get_citations(self, mock_request, client):
        """Test getting citations for a paper."""
        mock_request.return_value = {
            "results": [
                {
                    "id": "https://openalex.org/W3333",
                    "title": "Citing Paper"
                }
            ]
        }

        citations = client.get_citations("W1111", limit=10)

        assert len(citations) == 1
        assert citations[0].source == PaperSource.FORWARD

    @patch.object(OpenAlexClient, '_make_request')
    def test_get_citations_empty(self, mock_request, client):
        """Test getting citations when none exist."""
        mock_request.return_value = {"results": []}

        citations = client.get_citations("W1111")

        assert citations == []


class TestOpenAlexEnrichMetadata:
    """Tests for OpenAlex metadata enrichment."""

    @pytest.fixture
    def client(self):
        """Create an OpenAlex client instance."""
        return OpenAlexClient(rate_limit_delay=0)

    @patch.object(OpenAlexClient, 'get_paper_by_id')
    def test_enrich_metadata_with_openalex_id(self, mock_get, client):
        """Test enriching paper with OpenAlex ID."""
        existing_paper = Paper(
            id="test",
            title="Original Title",
            openalex_id="W1234567890",
            source=PaperSource.SEED
        )

        enriched_paper = Paper(
            id="enriched",
            title="Enriched Title",
            openalex_id="W1234567890",
            abstract="Enriched abstract",
            year=2023,
            citation_count=100,
            source=PaperSource.SEED
        )
        mock_get.return_value = enriched_paper

        result = client.enrich_metadata(existing_paper)

        assert result.abstract == "Enriched abstract"
        assert result.year == 2023
        assert result.citation_count == 100
        mock_get.assert_called_once_with("W1234567890")

    @patch.object(OpenAlexClient, 'get_paper_by_id')
    @patch.object(OpenAlexClient, 'search_by_doi')
    def test_enrich_metadata_falls_back_to_doi(self, mock_doi, mock_id, client):
        """Test enriching paper by DOI when no OpenAlex ID."""
        existing_paper = Paper(
            id="test",
            title="Test Paper",
            doi="10.1234/test",
            source=PaperSource.SEED
        )

        enriched_paper = Paper(
            id="enriched",
            title="Test Paper",
            openalex_id="W1111",
            source=PaperSource.SEED
        )
        mock_id.return_value = None
        mock_doi.return_value = enriched_paper

        result = client.enrich_metadata(existing_paper)

        assert result.openalex_id == "W1111"
        mock_doi.assert_called_once_with("10.1234/test")

    @patch.object(OpenAlexClient, 'search_by_title')
    def test_enrich_metadata_falls_back_to_title(self, mock_title, client):
        """Test enriching paper by title when no IDs."""
        existing_paper = Paper(
            id="test",
            title="Test Paper",
            source=PaperSource.SEED
        )

        enriched_paper = Paper(
            id="enriched",
            title="Test Paper",
            doi="10.1234/found",
            openalex_id="W2222",
            source=PaperSource.SEED
        )
        mock_title.return_value = enriched_paper

        result = client.enrich_metadata(existing_paper)

        assert result.doi == "10.1234/found"
        assert result.openalex_id == "W2222"
        mock_title.assert_called_once_with("Test Paper")


class TestOpenAlexMakeRequest:
    """Tests for OpenAlex API request handling."""

    @pytest.fixture
    def client(self):
        """Create an OpenAlex client instance."""
        return OpenAlexClient(rate_limit_delay=0)

    @patch('httpx.Client.get')
    def test_make_request_success(self, mock_get, client):
        """Test successful API request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "W1234"}
        mock_get.return_value = mock_response

        result = client._make_request("works/W1234")

        assert result == {"id": "W1234"}

    @patch('httpx.Client.get')
    def test_make_request_rate_limit(self, mock_get, client):
        """Test API request with rate limit error."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_get.return_value = mock_response

        with pytest.raises(RateLimitError):
            client._make_request("works/W1234")

    @patch('httpx.Client.get')
    def test_make_request_not_found(self, mock_get, client):
        """Test API request with 404 error."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        with pytest.raises(APINotFoundError):
            client._make_request("works/W9999")

    @patch('httpx.Client.get')
    def test_make_request_other_error(self, mock_get, client):
        """Test API request with other error status code."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        result = client._make_request("works/W1234")

        assert result == {}

    @patch('httpx.Client.get')
    def test_make_request_timeout(self, mock_get, client):
        """Test API request timeout handling."""
        import httpx
        mock_get.side_effect = httpx.TimeoutException("Timeout")

        result = client._make_request("works/W1234")

        assert result == {}
