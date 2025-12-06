"""Tests for Google Scholar client."""

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestGoogleScholarClient:
    """Tests for GoogleScholarClient."""

    def test_init_default_rate_limit(self):
        """Test default rate limit delay."""
        from snowball.apis.google_scholar import GoogleScholarClient
        client = GoogleScholarClient()
        assert client.rate_limit_delay == 5.0

    def test_init_custom_rate_limit(self):
        """Test custom rate limit delay."""
        from snowball.apis.google_scholar import GoogleScholarClient
        client = GoogleScholarClient(rate_limit_delay=10.0)
        assert client.rate_limit_delay == 10.0

    def test_titles_match_identical(self):
        """Test that identical titles match."""
        from snowball.apis.google_scholar import GoogleScholarClient
        client = GoogleScholarClient()
        assert client._titles_match("Test Paper Title", "Test Paper Title") is True

    def test_titles_match_case_insensitive(self):
        """Test that title matching is case insensitive."""
        from snowball.apis.google_scholar import GoogleScholarClient
        client = GoogleScholarClient()
        assert client._titles_match("Test Paper Title", "test paper title") is True

    def test_titles_match_with_stopwords(self):
        """Test that stopwords are ignored in matching."""
        from snowball.apis.google_scholar import GoogleScholarClient
        client = GoogleScholarClient()
        assert client._titles_match(
            "The Analysis of Machine Learning",
            "Analysis of Machine Learning"
        ) is True

    def test_titles_no_match(self):
        """Test that different titles don't match."""
        from snowball.apis.google_scholar import GoogleScholarClient
        client = GoogleScholarClient()
        assert client._titles_match(
            "Machine Learning in Healthcare",
            "Deep Learning for Computer Vision"
        ) is False

    @patch('snowball.apis.google_scholar.GoogleScholarClient._get_scholarly')
    def test_get_citation_count_found(self, mock_get_scholarly):
        """Test getting citation count when paper is found."""
        from snowball.apis.google_scholar import GoogleScholarClient

        # Mock scholarly
        mock_scholarly = MagicMock()
        mock_pub = {
            "bib": {"title": "Test Paper Title"},
            "num_citations": 42
        }
        mock_scholarly.search_pubs.return_value = iter([mock_pub])
        mock_get_scholarly.return_value = mock_scholarly

        client = GoogleScholarClient(rate_limit_delay=0)
        result = client.get_citation_count("Test Paper Title")

        assert result == 42

    @patch('snowball.apis.google_scholar.GoogleScholarClient._get_scholarly')
    def test_get_citation_count_not_found(self, mock_get_scholarly):
        """Test getting citation count when paper is not found."""
        from snowball.apis.google_scholar import GoogleScholarClient

        # Mock scholarly returning no results
        mock_scholarly = MagicMock()
        mock_scholarly.search_pubs.return_value = iter([])
        mock_get_scholarly.return_value = mock_scholarly

        client = GoogleScholarClient(rate_limit_delay=0)
        result = client.get_citation_count("Nonexistent Paper")

        assert result is None

    @patch('snowball.apis.google_scholar.GoogleScholarClient._get_scholarly')
    def test_get_citation_count_title_mismatch(self, mock_get_scholarly):
        """Test that mismatched titles return None."""
        from snowball.apis.google_scholar import GoogleScholarClient

        # Mock scholarly returning a different paper
        mock_scholarly = MagicMock()
        mock_pub = {
            "bib": {"title": "Completely Different Paper"},
            "num_citations": 100
        }
        mock_scholarly.search_pubs.return_value = iter([mock_pub])
        mock_get_scholarly.return_value = mock_scholarly

        client = GoogleScholarClient(rate_limit_delay=0)
        result = client.get_citation_count("Test Paper Title")

        assert result is None

    @patch('snowball.apis.google_scholar.GoogleScholarClient._get_scholarly')
    def test_get_citation_count_handles_error(self, mock_get_scholarly):
        """Test that errors are handled gracefully."""
        from snowball.apis.google_scholar import GoogleScholarClient

        # Mock scholarly raising an exception
        mock_scholarly = MagicMock()
        mock_scholarly.search_pubs.side_effect = Exception("Network error")
        mock_get_scholarly.return_value = mock_scholarly

        client = GoogleScholarClient(rate_limit_delay=0)
        result = client.get_citation_count("Test Paper")

        assert result is None

    @patch('snowball.apis.google_scholar.GoogleScholarClient._get_scholarly')
    def test_get_citation_count_with_metadata(self, mock_get_scholarly):
        """Test getting citation count with metadata."""
        from snowball.apis.google_scholar import GoogleScholarClient

        mock_scholarly = MagicMock()
        mock_pub = {
            "bib": {"title": "Test Paper Title", "pub_year": "2023"},
            "num_citations": 42,
            "pub_url": "https://example.com/paper"
        }
        mock_scholarly.search_pubs.return_value = iter([mock_pub])
        mock_get_scholarly.return_value = mock_scholarly

        client = GoogleScholarClient(rate_limit_delay=0)
        citations, metadata = client.get_citation_count_with_metadata("Test Paper Title")

        assert citations == 42
        assert metadata["google_scholar_title"] == "Test Paper Title"
        assert metadata["google_scholar_year"] == "2023"
        assert metadata["google_scholar_url"] == "https://example.com/paper"
