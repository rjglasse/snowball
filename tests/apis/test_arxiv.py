"""Tests for arXiv API client."""

import pytest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

from snowball.apis.arxiv import ArXivClient
from snowball.models import Paper, PaperSource


class TestArXivClient:
    """Tests for ArXivClient class."""

    @pytest.fixture
    def client(self):
        """Create an arXiv client instance with no delay."""
        return ArXivClient(rate_limit_delay=0)

    @pytest.fixture
    def mock_arxiv_entry_xml(self):
        """Create a mock arXiv API response entry."""
        return """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
            <entry>
                <id>http://arxiv.org/abs/2301.00001v1</id>
                <title>A Test Paper on Machine Learning</title>
                <summary>This is the abstract of the test paper about machine learning.</summary>
                <published>2023-01-15T12:00:00Z</published>
                <author>
                    <name>John Doe</name>
                </author>
                <author>
                    <name>Jane Smith</name>
                </author>
                <arxiv:doi>10.1234/test.doi</arxiv:doi>
                <arxiv:primary_category term="cs.LG"/>
            </entry>
        </feed>
        """

    @pytest.fixture
    def mock_arxiv_empty_response(self):
        """Create an empty arXiv API response."""
        return """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
        </feed>
        """

    def test_init(self, client):
        """Test client initialization."""
        assert client.rate_limit_delay == 0
        assert client.client is not None

    @patch.object(ArXivClient, '_make_request')
    def test_search_by_arxiv_id(self, mock_request, client, mock_arxiv_entry_xml):
        """Test searching for a paper by arXiv ID."""
        mock_request.return_value = mock_arxiv_entry_xml

        paper = client.search_by_arxiv_id("2301.00001")

        assert paper is not None
        assert paper.title == "A Test Paper on Machine Learning"
        assert paper.arxiv_id == "2301.00001"
        mock_request.assert_called_once_with({"id_list": "2301.00001"})

    @patch.object(ArXivClient, '_make_request')
    def test_search_by_arxiv_id_not_found(self, mock_request, client, mock_arxiv_empty_response):
        """Test searching for an arXiv ID that doesn't exist."""
        mock_request.return_value = mock_arxiv_empty_response

        paper = client.search_by_arxiv_id("9999.99999")

        assert paper is None

    @patch.object(ArXivClient, '_make_request')
    def test_search_by_arxiv_id_returns_none_on_empty_response(self, mock_request, client):
        """Test that empty response returns None."""
        mock_request.return_value = ""

        paper = client.search_by_arxiv_id("2301.00001")

        assert paper is None

    def test_search_by_doi_returns_none(self, client):
        """Test that search_by_doi returns None (arXiv doesn't support DOI search well)."""
        result = client.search_by_doi("10.1234/test")
        assert result is None

    @patch.object(ArXivClient, '_make_request')
    def test_search_by_title(self, mock_request, client, mock_arxiv_entry_xml):
        """Test searching for a paper by title."""
        mock_request.return_value = mock_arxiv_entry_xml

        paper = client.search_by_title("Machine Learning Test")

        assert paper is not None
        mock_request.assert_called_once()

    @patch.object(ArXivClient, '_make_request')
    def test_search_by_title_not_found(self, mock_request, client, mock_arxiv_empty_response):
        """Test searching by title with no results."""
        mock_request.return_value = mock_arxiv_empty_response

        paper = client.search_by_title("Nonexistent Paper Title")

        assert paper is None

    def test_get_references_returns_empty(self, client):
        """Test that get_references returns empty list (not supported by arXiv)."""
        result = client.get_references("2301.00001")
        assert result == []

    def test_get_citations_returns_empty(self, client):
        """Test that get_citations returns empty list (not supported by arXiv)."""
        result = client.get_citations("2301.00001")
        assert result == []


class TestArXivParseEntry:
    """Tests for parsing arXiv entry XML."""

    @pytest.fixture
    def client(self):
        """Create an arXiv client instance."""
        return ArXivClient(rate_limit_delay=0)

    def test_parse_entry_extracts_all_fields(self, client):
        """Test that _parse_entry extracts all fields correctly."""
        entry_xml = """
        <entry xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
            <id>http://arxiv.org/abs/2301.00001v1</id>
            <title>Test Paper Title</title>
            <summary>Test abstract text.</summary>
            <published>2023-01-15T12:00:00Z</published>
            <author>
                <name>John Doe</name>
            </author>
            <author>
                <name>Jane Smith</name>
            </author>
            <arxiv:doi>10.1234/test.doi</arxiv:doi>
            <arxiv:primary_category term="cs.ML"/>
        </entry>
        """
        entry = ET.fromstring(entry_xml)

        paper = client._parse_entry(entry)

        assert paper is not None
        assert paper.title == "Test Paper Title"
        assert paper.arxiv_id == "2301.00001"
        assert paper.abstract == "Test abstract text."
        assert paper.year == 2023
        assert paper.doi == "10.1234/test.doi"
        assert len(paper.authors) == 2
        assert paper.authors[0].name == "John Doe"
        assert paper.venue is not None
        assert "cs.ML" in paper.venue.name
        assert paper.venue.type == "preprint"

    def test_parse_entry_handles_missing_fields(self, client):
        """Test that _parse_entry handles missing optional fields."""
        entry_xml = """
        <entry xmlns="http://www.w3.org/2005/Atom">
            <id>http://arxiv.org/abs/2301.00002v1</id>
            <title>Minimal Paper</title>
        </entry>
        """
        entry = ET.fromstring(entry_xml)

        paper = client._parse_entry(entry)

        assert paper is not None
        assert paper.title == "Minimal Paper"
        assert paper.arxiv_id == "2301.00002"
        assert paper.doi is None
        assert paper.authors == []

    def test_parse_entry_with_custom_source(self, client):
        """Test parsing entry with custom source."""
        entry_xml = """
        <entry xmlns="http://www.w3.org/2005/Atom">
            <id>http://arxiv.org/abs/2301.00003v1</id>
            <title>Test Paper</title>
        </entry>
        """
        entry = ET.fromstring(entry_xml)

        paper = client._parse_entry(entry, source=PaperSource.BACKWARD)

        assert paper.source == PaperSource.BACKWARD


class TestArXivEnrichMetadata:
    """Tests for arXiv metadata enrichment."""

    @pytest.fixture
    def client(self):
        """Create an arXiv client instance."""
        return ArXivClient(rate_limit_delay=0)

    @patch.object(ArXivClient, 'search_by_arxiv_id')
    def test_enrich_metadata_with_arxiv_id(self, mock_search, client):
        """Test enriching paper with arXiv ID."""
        existing_paper = Paper(
            id="test",
            title="Original Title",
            arxiv_id="2301.00001",
            source=PaperSource.SEED
        )

        enriched_paper = Paper(
            id="enriched",
            title="Enriched Title",
            arxiv_id="2301.00001",
            abstract="Enriched abstract",
            year=2023,
            source=PaperSource.SEED
        )
        mock_search.return_value = enriched_paper

        result = client.enrich_metadata(existing_paper)

        assert result.abstract == "Enriched abstract"
        assert result.year == 2023
        mock_search.assert_called_once_with("2301.00001")

    @patch.object(ArXivClient, 'search_by_arxiv_id')
    @patch.object(ArXivClient, 'search_by_title')
    def test_enrich_metadata_falls_back_to_title(self, mock_title, mock_arxiv_id, client):
        """Test enriching paper by title when no arXiv ID."""
        existing_paper = Paper(
            id="test",
            title="Test Paper",
            source=PaperSource.SEED
        )

        enriched_paper = Paper(
            id="enriched",
            title="Test Paper",
            arxiv_id="2301.00002",
            abstract="Found abstract",
            source=PaperSource.SEED
        )
        mock_arxiv_id.return_value = None
        mock_title.return_value = enriched_paper

        result = client.enrich_metadata(existing_paper)

        assert result.arxiv_id == "2301.00002"
        assert result.abstract == "Found abstract"
        mock_title.assert_called_once_with("Test Paper")

    @patch.object(ArXivClient, 'search_by_arxiv_id')
    def test_enrich_metadata_no_result(self, mock_search, client):
        """Test enriching paper when no result found."""
        existing_paper = Paper(
            id="test",
            title="Unknown Paper",
            arxiv_id="9999.99999",
            source=PaperSource.SEED
        )
        mock_search.return_value = None

        result = client.enrich_metadata(existing_paper)

        # Should return paper unchanged
        assert result.title == "Unknown Paper"
        assert result.abstract is None


class TestArXivMakeRequest:
    """Tests for arXiv API request handling."""

    @pytest.fixture
    def client(self):
        """Create an arXiv client instance."""
        return ArXivClient(rate_limit_delay=0)

    @patch('httpx.Client.get')
    def test_make_request_success(self, mock_get, client):
        """Test successful API request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "<feed></feed>"
        mock_get.return_value = mock_response

        result = client._make_request({"id_list": "2301.00001"})

        assert result == "<feed></feed>"

    @patch('httpx.Client.get')
    def test_make_request_error_status(self, mock_get, client):
        """Test API request with error status code."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        result = client._make_request({"id_list": "2301.00001"})

        assert result == ""

    @patch('httpx.Client.get')
    def test_make_request_timeout(self, mock_get, client):
        """Test API request timeout handling."""
        import httpx
        mock_get.side_effect = httpx.TimeoutException("Timeout")

        result = client._make_request({"id_list": "2301.00001"})

        assert result == ""
