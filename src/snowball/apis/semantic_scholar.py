"""Semantic Scholar API client."""

import logging
import time
from typing import Optional, List, Dict, Any
import httpx

from .base import BaseAPIClient, RateLimitError, APINotFoundError
from ..models import Paper, Author, Venue, PaperSource
from ..storage.json_storage import JSONStorage

logger = logging.getLogger(__name__)


class SemanticScholarClient(BaseAPIClient):
    """Client for Semantic Scholar API."""

    BASE_URL = "https://api.semanticscholar.org/graph/v1"

    # Fields to request from the API
    PAPER_FIELDS = [
        "paperId",
        "externalIds",
        "title",
        "abstract",
        "venue",
        "year",
        "authors",
        "citationCount",
        "influentialCitationCount",
        "references",
        "citations",
        "publicationTypes",
        "publicationDate",
        "journal",
    ]

    def __init__(self, api_key: Optional[str] = None, rate_limit_delay: Optional[float] = None):
        """Initialize Semantic Scholar client.

        Args:
            api_key: Optional API key for authenticated access
            rate_limit_delay: Delay between requests in seconds. Defaults to 2.0s.
        """
        self.api_key = api_key
        # S2 rate limits: be conservative to avoid 429 errors
        if rate_limit_delay is not None:
            self.rate_limit_delay = rate_limit_delay
        else:
            self.rate_limit_delay = 0.5   # 0.5 seconds between requests (safe for single enrichments)
        self.client = httpx.Client(timeout=30.0)

        if api_key:
            self.client.headers["x-api-key"] = api_key

    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Make a request to the Semantic Scholar API.

        Args:
            endpoint: API endpoint
            params: Query parameters

        Returns:
            JSON response

        Raises:
            RateLimitError: If rate limit is exceeded
            APINotFoundError: If resource not found
        """
        url = f"{self.BASE_URL}/{endpoint}"

        try:
            time.sleep(self.rate_limit_delay)
            response = self.client.get(url, params=params)

            if response.status_code == 429:
                raise RateLimitError("Semantic Scholar rate limit exceeded")
            elif response.status_code == 404:
                raise APINotFoundError(f"Resource not found: {endpoint}")
            elif response.status_code != 200:
                logger.error(f"API error: {response.status_code} - {response.text}")
                return {}

            return response.json()

        except httpx.TimeoutException:
            logger.warning(f"Timeout requesting {url}")
            return {}

    def _parse_paper(self, data: Dict[str, Any], source: PaperSource = PaperSource.SEED) -> Paper:
        """Parse Semantic Scholar API response into a Paper object.

        Args:
            data: API response data
            source: Source of this paper

        Returns:
            Paper object
        """
        # Extract external IDs
        external_ids = data.get("externalIds", {}) or {}
        doi = external_ids.get("DOI")
        arxiv_id = external_ids.get("ArXiv")
        pmid = external_ids.get("PubMed")

        # Parse authors
        authors = []
        for author_data in data.get("authors", []):
            author = Author(
                name=author_data.get("name", "Unknown"),
                affiliations=[]
            )
            authors.append(author)

        # Parse venue
        venue_name = data.get("venue") or data.get("journal", {}).get("name")
        venue = None
        if venue_name:
            venue = Venue(
                name=venue_name,
                year=data.get("year"),
                type=None  # S2 doesn't always provide this
            )

        # Create paper
        paper = Paper(
            id=JSONStorage.generate_id(),
            semantic_scholar_id=data.get("paperId"),
            doi=doi,
            arxiv_id=arxiv_id,
            pmid=pmid,
            title=data.get("title", "Unknown Title"),
            authors=authors,
            year=data.get("year"),
            abstract=data.get("abstract"),
            venue=venue,
            citation_count=data.get("citationCount"),
            influential_citation_count=data.get("influentialCitationCount"),
            source=source,
            raw_data={"semantic_scholar": data}
        )

        return paper

    def search_by_doi(self, doi: str) -> Optional[Paper]:
        """Search for a paper by DOI."""
        try:
            data = self._make_request(
                f"paper/DOI:{doi}",
                params={"fields": ",".join(self.PAPER_FIELDS)}
            )
            if data:
                return self._parse_paper(data)
        except APINotFoundError:
            logger.info(f"Paper not found for DOI: {doi}")
        except Exception as e:
            logger.error(f"Error searching by DOI {doi}: {e}")

        return None

    def search_by_title(self, title: str) -> Optional[Paper]:
        """Search for a paper by title."""
        try:
            data = self._make_request(
                "paper/search",
                params={
                    "query": title,
                    "fields": ",".join(self.PAPER_FIELDS),
                    "limit": 1
                }
            )

            if data and data.get("data"):
                paper_data = data["data"][0]
                return self._parse_paper(paper_data)

        except Exception as e:
            logger.error(f"Error searching by title '{title}': {e}")

        return None

    def get_paper_by_id(self, paper_id: str) -> Optional[Paper]:
        """Get a paper by Semantic Scholar ID."""
        try:
            data = self._make_request(
                f"paper/{paper_id}",
                params={"fields": ",".join(self.PAPER_FIELDS)}
            )
            if data:
                return self._parse_paper(data)
        except APINotFoundError:
            logger.info(f"Paper not found for ID: {paper_id}")
        except Exception as e:
            logger.error(f"Error getting paper {paper_id}: {e}")

        return None

    def get_references(self, paper_id: str, limit: int = 1000) -> List[Paper]:
        """Get papers referenced by this paper."""
        references = []

        try:
            # S2 API returns references in batches
            offset = 0
            batch_size = 100

            while offset < limit:
                data = self._make_request(
                    f"paper/{paper_id}/references",
                    params={
                        "fields": ",".join(self.PAPER_FIELDS),
                        "limit": min(batch_size, limit - offset),
                        "offset": offset
                    }
                )

                if not data or "data" not in data:
                    break

                for ref in data["data"]:
                    cited_paper_data = ref.get("citedPaper")
                    if cited_paper_data:
                        paper = self._parse_paper(cited_paper_data, source=PaperSource.BACKWARD)
                        references.append(paper)

                # Check if there are more results
                if len(data["data"]) < batch_size:
                    break

                offset += batch_size

        except Exception as e:
            logger.error(f"Error getting references for {paper_id}: {e}")

        logger.info(f"Found {len(references)} references for paper {paper_id}")
        return references

    def get_citations(self, paper_id: str, limit: int = 1000) -> List[Paper]:
        """Get papers citing this paper."""
        citations = []

        try:
            # S2 API returns citations in batches
            offset = 0
            batch_size = 100

            while offset < limit:
                data = self._make_request(
                    f"paper/{paper_id}/citations",
                    params={
                        "fields": ",".join(self.PAPER_FIELDS),
                        "limit": min(batch_size, limit - offset),
                        "offset": offset
                    }
                )

                if not data or "data" not in data:
                    break

                for cit in data["data"]:
                    citing_paper_data = cit.get("citingPaper")
                    if citing_paper_data:
                        paper = self._parse_paper(citing_paper_data, source=PaperSource.FORWARD)
                        citations.append(paper)

                # Check if there are more results
                if len(data["data"]) < batch_size:
                    break

                offset += batch_size

        except Exception as e:
            logger.error(f"Error getting citations for {paper_id}: {e}")

        logger.info(f"Found {len(citations)} citations for paper {paper_id}")
        return citations

    def enrich_metadata(self, paper: Paper) -> Paper:
        """Enrich paper metadata using Semantic Scholar."""
        # Try to find the paper using available identifiers
        s2_paper = None

        if paper.semantic_scholar_id:
            s2_paper = self.get_paper_by_id(paper.semantic_scholar_id)
        elif paper.doi:
            s2_paper = self.search_by_doi(paper.doi)
        elif paper.title:
            s2_paper = self.search_by_title(paper.title)

        if s2_paper:
            # Merge data, preferring non-null values
            if not paper.title or paper.title == "Unknown Title":
                paper.title = s2_paper.title
            if not paper.abstract:
                paper.abstract = s2_paper.abstract
            if not paper.year:
                paper.year = s2_paper.year
            if not paper.authors:
                paper.authors = s2_paper.authors
            if not paper.venue:
                paper.venue = s2_paper.venue
            if not paper.citation_count:
                paper.citation_count = s2_paper.citation_count
            if not paper.influential_citation_count:
                paper.influential_citation_count = s2_paper.influential_citation_count
            if not paper.semantic_scholar_id:
                paper.semantic_scholar_id = s2_paper.semantic_scholar_id
            if not paper.doi:
                paper.doi = s2_paper.doi
            if not paper.arxiv_id:
                paper.arxiv_id = s2_paper.arxiv_id

            # Merge raw data
            paper.raw_data.update(s2_paper.raw_data)

        return paper

    def __del__(self):
        """Close the HTTP client."""
        self.client.close()
