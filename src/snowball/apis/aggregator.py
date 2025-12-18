"""API aggregator that combines multiple academic APIs."""

import logging
import uuid
from typing import Optional, List, Dict
from ..models import Paper, PaperSource, Author
from ..paper_utils import titles_match

from .semantic_scholar import SemanticScholarClient
from .crossref import CrossRefClient
from .openalex import OpenAlexClient
from .arxiv import ArXivClient
from .google_scholar import GoogleScholarClient

logger = logging.getLogger(__name__)


class APIAggregator:
    """Aggregates multiple academic APIs for comprehensive coverage."""

    def __init__(
        self,
        s2_api_key: Optional[str] = None,
        email: Optional[str] = None,
        use_apis: Optional[List[str]] = None,
        scholar_proxy: Optional[str] = None,
        scholar_free_proxy: bool = False,
    ):
        """Initialize API aggregator.

        Args:
            s2_api_key: Semantic Scholar API key
            email: Email for CrossRef and OpenAlex polite pools
            use_apis: List of APIs to use (default: all)
            scholar_proxy: Proxy URL for Google Scholar (e.g., "http://host:port")
            scholar_free_proxy: Use free rotating proxies for Google Scholar
        """
        if use_apis is None:
            # Note: google_scholar excluded by default due to aggressive rate limiting/IP bans
            # Use --use-scholar flag to explicitly enable it
            use_apis = ["semantic_scholar", "crossref", "openalex", "arxiv"]

        self.clients = {}

        # Initialize enabled API clients
        if "semantic_scholar" in use_apis:
            self.clients["semantic_scholar"] = SemanticScholarClient(api_key=s2_api_key)
            logger.info("Initialized Semantic Scholar client")

        if "crossref" in use_apis:
            self.clients["crossref"] = CrossRefClient(email=email)
            logger.info("Initialized CrossRef client")

        if "openalex" in use_apis:
            self.clients["openalex"] = OpenAlexClient(email=email)
            logger.info("Initialized OpenAlex client")

        if "arxiv" in use_apis:
            self.clients["arxiv"] = ArXivClient()
            logger.info("Initialized arXiv client")

        if "google_scholar" in use_apis:
            self.clients["google_scholar"] = GoogleScholarClient(
                proxy=scholar_proxy,
                use_free_proxy=scholar_free_proxy,
            )
            logger.info("Initialized Google Scholar client")

    def search_by_doi(self, doi: str) -> Optional[Paper]:
        """Search for a paper by DOI across all APIs.

        Tries APIs in order of preference: Semantic Scholar, OpenAlex, CrossRef.
        """
        for api_name in ["semantic_scholar", "openalex", "crossref"]:
            if api_name in self.clients:
                try:
                    paper = self.clients[api_name].search_by_doi(doi)
                    if paper:
                        logger.info(f"Found paper with DOI {doi} using {api_name}")
                        # Enrich with other APIs
                        return self.enrich_metadata(paper)
                except Exception as e:
                    logger.warning(f"Error searching {api_name} by DOI: {e}")

        logger.warning(f"Paper not found for DOI: {doi}")
        return None

    def search_by_title(self, title: str) -> Optional[Paper]:
        """Search for a paper by title across all APIs.

        Tries APIs in order of preference. Only returns papers whose
        title matches the search query (using title similarity).
        """
        for api_name in ["semantic_scholar", "openalex", "crossref", "arxiv"]:
            if api_name in self.clients:
                try:
                    paper = self.clients[api_name].search_by_title(title)
                    if paper and paper.title:
                        # Validate that the found paper's title actually matches
                        if titles_match(title, paper.title):
                            logger.info(f"Found paper '{title}' using {api_name}")
                            # Enrich with other APIs
                            return self.enrich_metadata(paper)
                        else:
                            logger.debug(
                                f"{api_name} returned non-matching title: "
                                f"searched '{title}', got '{paper.title}'"
                            )
                except Exception as e:
                    logger.warning(f"Error searching {api_name} by title: {e}")

        logger.warning(f"Paper not found for title: {title}")
        return None

    def get_references(self, paper: Paper, limit: int = 1000) -> List[Paper]:
        """Get references for a paper using the best available API.

        Prefers Semantic Scholar, then OpenAlex.
        """
        references = []

        # Try Semantic Scholar first
        if "semantic_scholar" in self.clients and paper.semantic_scholar_id:
            try:
                references = self.clients["semantic_scholar"].get_references(
                    paper.semantic_scholar_id, limit
                )
                if references:
                    logger.info(f"Found {len(references)} references using Semantic Scholar")
                    return references
            except Exception as e:
                logger.warning(f"Error getting S2 references: {e}")

        # Try OpenAlex
        if "openalex" in self.clients and paper.openalex_id:
            try:
                references = self.clients["openalex"].get_references(
                    paper.openalex_id, limit
                )
                if references:
                    logger.info(f"Found {len(references)} references using OpenAlex")
                    return references
            except Exception as e:
                logger.warning(f"Error getting OpenAlex references: {e}")

        logger.warning(f"Could not find references for paper: {paper.title}")
        return []

    def get_citations(self, paper: Paper, limit: int = 1000) -> List[Paper]:
        """Get citations for a paper using the best available API.

        Prefers Semantic Scholar, then OpenAlex, then Google Scholar.
        """
        citations = []

        # Try Semantic Scholar first
        if "semantic_scholar" in self.clients and paper.semantic_scholar_id:
            try:
                citations = self.clients["semantic_scholar"].get_citations(
                    paper.semantic_scholar_id, limit
                )
                if citations:
                    logger.info(f"Found {len(citations)} citations using Semantic Scholar")
                    return citations
            except Exception as e:
                logger.warning(f"Error getting S2 citations: {e}")

        # Try OpenAlex
        if "openalex" in self.clients and paper.openalex_id:
            try:
                citations = self.clients["openalex"].get_citations(
                    paper.openalex_id, limit
                )
                if citations:
                    logger.info(f"Found {len(citations)} citations using OpenAlex")
                    return citations
            except Exception as e:
                logger.warning(f"Error getting OpenAlex citations: {e}")

        # Try Google Scholar as fallback (slower, rate-limited)
        if "google_scholar" in self.clients and paper.title:
            try:
                # Google Scholar returns dicts, convert to Paper objects
                gs_limit = min(limit, 50)  # Limit GS to 50 due to rate limiting
                gs_citations = self.clients["google_scholar"].get_citations(
                    paper.title, gs_limit
                )
                if gs_citations:
                    citations = self._convert_gs_citations_to_papers(gs_citations)
                    logger.info(f"Found {len(citations)} citations using Google Scholar")
                    return citations
            except Exception as e:
                logger.warning(f"Error getting Google Scholar citations: {e}")

        logger.warning(f"Could not find citations for paper: {paper.title}")
        return []

    def _convert_gs_citations_to_papers(self, gs_citations: List[dict]) -> List[Paper]:
        """Convert Google Scholar citation dicts to Paper objects."""
        papers = []
        for cit in gs_citations:
            if not cit.get("title"):
                continue

            # Convert authors list to Author objects
            authors = []
            for author_name in cit.get("authors", []):
                if author_name:
                    authors.append(Author(name=author_name.strip()))

            paper = Paper(
                id=str(uuid.uuid4()),
                title=cit["title"],
                year=cit.get("year"),
                authors=authors,
                citation_count=cit.get("num_citations"),
                source=PaperSource.FORWARD,
                raw_data={"google_scholar": cit}
            )
            papers.append(paper)

        return papers

    def enrich_metadata(self, paper: Paper) -> Paper:
        """Enrich paper metadata using all available APIs."""
        for api_name, client in self.clients.items():
            if not hasattr(client, 'enrich_metadata'):
                continue
            try:
                paper = client.enrich_metadata(paper)
            except Exception as e:
                logger.warning(f"Error enriching with {api_name}: {e}")

        return paper

    def identify_paper(self, paper: Paper) -> Paper:
        """Try to identify a paper and fill in missing API IDs."""
        # If we have a DOI but missing other IDs, search by DOI
        if paper.doi and not (paper.semantic_scholar_id and paper.openalex_id):
            found_paper = self.search_by_doi(paper.doi)
            if found_paper:
                # Copy over the IDs
                if not paper.semantic_scholar_id:
                    paper.semantic_scholar_id = found_paper.semantic_scholar_id
                if not paper.openalex_id:
                    paper.openalex_id = found_paper.openalex_id
                if not paper.arxiv_id:
                    paper.arxiv_id = found_paper.arxiv_id

        # If we only have a title, search by title
        elif paper.title and not paper.doi:
            found_paper = self.search_by_title(paper.title)
            if found_paper and found_paper.title:
                # Validate that titles actually match before copying identifiers
                if titles_match(paper.title, found_paper.title):
                    # Merge identifiers
                    if not paper.doi:
                        paper.doi = found_paper.doi
                    if not paper.semantic_scholar_id:
                        paper.semantic_scholar_id = found_paper.semantic_scholar_id
                    if not paper.openalex_id:
                        paper.openalex_id = found_paper.openalex_id
                    if not paper.arxiv_id:
                        paper.arxiv_id = found_paper.arxiv_id
                else:
                    logger.warning(
                        f"Title mismatch - searched for '{paper.title}' "
                        f"but found '{found_paper.title}'. Skipping identifier merge."
                    )

        return paper
