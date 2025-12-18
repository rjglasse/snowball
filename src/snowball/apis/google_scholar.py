"""Google Scholar client for citation data."""

import logging
import time
from typing import Optional, Tuple, List

logger = logging.getLogger(__name__)


class GoogleScholarClient:
    """Client for fetching citation counts from Google Scholar.

    Uses the scholarly library to scrape Google Scholar.
    Note: This is scraping, not an official API. Use responsibly with
    appropriate rate limiting to avoid being blocked.
    """

    def __init__(
        self,
        rate_limit_delay: float = 2.0,
        proxy: Optional[str] = None,
        use_free_proxy: bool = False,
    ):
        """Initialize Google Scholar client.

        Args:
            rate_limit_delay: Delay between requests in seconds.
                              Default is 2 seconds to avoid rate limiting.
            proxy: HTTP/HTTPS proxy URL (e.g., "http://user:pass@host:port")
            use_free_proxy: Use free rotating proxies via free-proxy library
        """
        self.rate_limit_delay = rate_limit_delay
        self.proxy = proxy
        self.use_free_proxy = use_free_proxy
        self._scholarly = None
        self._last_request_time = 0
        self._proxy_configured = False

    def _get_scholarly(self):
        """Lazy load scholarly library and configure proxy if needed."""
        if self._scholarly is None:
            try:
                from scholarly import scholarly
                self._scholarly = scholarly
            except ImportError:
                logger.error("scholarly library not installed. Run: pip install scholarly")
                raise ImportError("scholarly library required for Google Scholar support")

        # Configure proxy on first use
        if not self._proxy_configured:
            self._configure_proxy()
            self._proxy_configured = True

        return self._scholarly

    def _configure_proxy(self):
        """Configure proxy for scholarly requests."""
        if not self.proxy and not self.use_free_proxy:
            return

        try:
            from scholarly import ProxyGenerator
            pg = ProxyGenerator()

            if self.proxy:
                # Use specified proxy
                success = pg.SingleProxy(http=self.proxy, https=self.proxy)
                if success:
                    self._scholarly.use_proxy(pg)
                    logger.info(f"Google Scholar: Using proxy {self.proxy[:30]}...")
                else:
                    logger.warning("Failed to configure proxy, continuing without")
            elif self.use_free_proxy:
                # Use free rotating proxies
                success = pg.FreeProxies()
                if success:
                    self._scholarly.use_proxy(pg)
                    logger.info("Google Scholar: Using free rotating proxies")
                else:
                    logger.warning("Failed to configure free proxy, continuing without")

        except ImportError:
            logger.warning("ProxyGenerator not available, continuing without proxy")
        except Exception as e:
            logger.warning(f"Proxy configuration failed: {e}")

    def _rate_limit(self):
        """Apply rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    def get_citation_count(self, title: str) -> Optional[int]:
        """Get citation count for a paper by title.

        Args:
            title: Paper title to search for

        Returns:
            Citation count if found, None otherwise
        """
        try:
            self._rate_limit()
            scholarly = self._get_scholarly()

            # Search for the paper
            search_query = scholarly.search_pubs(title)
            pub = next(search_query, None)

            if pub:
                # Verify title similarity to avoid false matches
                found_title = pub.get("bib", {}).get("title", "").lower()
                if self._titles_match(title.lower(), found_title):
                    citations = pub.get("num_citations")
                    if citations is not None:
                        logger.info(f"Google Scholar: {title[:50]}... -> {citations} citations")
                        return int(citations)
                else:
                    logger.debug(f"Title mismatch: '{title[:30]}' vs '{found_title[:30]}'")

            logger.debug(f"No Google Scholar match for: {title[:50]}")
            return None

        except StopIteration:
            return None
        except Exception as e:
            logger.warning(f"Google Scholar error for '{title[:50]}': {e}")
            return None

    def get_citation_count_with_metadata(self, title: str) -> Tuple[Optional[int], Optional[dict]]:
        """Get citation count and additional metadata for a paper.

        Args:
            title: Paper title to search for

        Returns:
            Tuple of (citation_count, metadata_dict) or (None, None) if not found
        """
        try:
            self._rate_limit()
            scholarly = self._get_scholarly()

            search_query = scholarly.search_pubs(title)
            pub = next(search_query, None)

            if pub:
                found_title = pub.get("bib", {}).get("title", "").lower()
                if self._titles_match(title.lower(), found_title):
                    citations = pub.get("num_citations")
                    metadata = {
                        "google_scholar_title": pub.get("bib", {}).get("title"),
                        "google_scholar_year": pub.get("bib", {}).get("pub_year"),
                        "google_scholar_url": pub.get("pub_url"),
                        "google_scholar_citations": citations,
                    }
                    return int(citations) if citations else None, metadata

            return None, None

        except Exception as e:
            logger.warning(f"Google Scholar error: {e}")
            return None, None

    def _titles_match(self, title1: str, title2: str, threshold: float = 0.8) -> bool:
        """Check if two titles are similar enough to be the same paper.

        Uses simple word overlap ratio for matching.
        """
        # Normalize titles
        words1 = set(title1.lower().split())
        words2 = set(title2.lower().split())

        # Remove common short words
        stopwords = {'a', 'an', 'the', 'of', 'in', 'on', 'for', 'to', 'and', 'or', 'with'}
        words1 = words1 - stopwords
        words2 = words2 - stopwords

        if not words1 or not words2:
            return False

        # Calculate Jaccard similarity
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        similarity = intersection / union if union > 0 else 0

        return similarity >= threshold

    def get_citations(self, title: str, limit: int = 50) -> List[dict]:
        """Get papers that cite a given paper (forward citations).

        Args:
            title: Paper title to search for
            limit: Maximum number of citing papers to return

        Returns:
            List of dicts with citing paper metadata (title, year, authors, etc.)
        """
        try:
            self._rate_limit()
            scholarly = self._get_scholarly()

            # First find the paper
            search_query = scholarly.search_pubs(title)
            pub = next(search_query, None)

            if not pub:
                logger.debug(f"No Google Scholar match for: {title[:50]}")
                return []

            found_title = pub.get("bib", {}).get("title", "").lower()
            if not self._titles_match(title.lower(), found_title):
                logger.debug(f"Title mismatch: '{title[:30]}' vs '{found_title[:30]}'")
                return []

            num_citations = pub.get("num_citations", 0)
            if not num_citations:
                logger.debug(f"No citations for: {title[:50]}")
                return []

            logger.info(f"Google Scholar: Found {num_citations} citations for '{title[:50]}...'")

            # Get citing papers
            citations = []
            try:
                self._rate_limit()
                citedby = scholarly.citedby(pub)

                for i, citing_pub in enumerate(citedby):
                    if i >= limit:
                        break

                    self._rate_limit()
                    bib = citing_pub.get("bib", {})

                    citation = {
                        "title": bib.get("title"),
                        "year": int(bib.get("pub_year")) if bib.get("pub_year") else None,
                        "authors": bib.get("author", "").split(" and ") if bib.get("author") else [],
                        "venue": bib.get("venue"),
                        "url": citing_pub.get("pub_url"),
                        "num_citations": citing_pub.get("num_citations"),
                    }

                    if citation["title"]:
                        citations.append(citation)
                        logger.debug(f"  Citation {i+1}: {citation['title'][:50]}...")

            except Exception as e:
                logger.warning(f"Error fetching citing papers: {e}")

            logger.info(f"Google Scholar: Retrieved {len(citations)} citing papers")
            return citations

        except StopIteration:
            return []
        except Exception as e:
            logger.warning(f"Google Scholar citation error for '{title[:50]}': {e}")
            return []
