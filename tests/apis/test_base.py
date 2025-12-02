"""Tests for base API client interface."""

import pytest

from snowball.apis.base import BaseAPIClient, APIClientError, RateLimitError, APINotFoundError
from snowball.models import Paper


class TestAPIClientErrors:
    """Tests for API client error classes."""

    def test_api_client_error(self):
        """Test base APIClientError."""
        error = APIClientError("Test error message")
        assert str(error) == "Test error message"

    def test_rate_limit_error(self):
        """Test RateLimitError."""
        error = RateLimitError("Rate limit exceeded")
        assert isinstance(error, APIClientError)
        assert str(error) == "Rate limit exceeded"

    def test_api_not_found_error(self):
        """Test APINotFoundError."""
        error = APINotFoundError("Resource not found")
        assert isinstance(error, APIClientError)
        assert str(error) == "Resource not found"


class TestBaseAPIClient:
    """Tests for BaseAPIClient abstract class."""

    def test_cannot_instantiate_directly(self):
        """Test that BaseAPIClient cannot be instantiated."""
        with pytest.raises(TypeError):
            BaseAPIClient()

    def test_subclass_requires_methods(self):
        """Test that subclasses must implement abstract methods."""
        class IncompleteClient(BaseAPIClient):
            pass

        with pytest.raises(TypeError):
            IncompleteClient()
