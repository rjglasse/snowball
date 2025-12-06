"""Google Scholar client for citation data."""

import logging
import time
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class GoogleScholarClient:
    """Client for fetching citation counts from Google Scholar.

    Uses the scholarly library to scrape Google Scholar.
    Note: This is scraping, not an official API. Use responsibly with
    appropriate rate limiting to avoid being blocked.
    """

    def __init__(self, rate_limit_delay: float = 5.0):
        """Initialize Google Scholar client.

        Args:
            rate_limit_delay: Delay between requests in seconds.
                              Default is 5 seconds to avoid rate limiting.
        """
        self.rate_limit_delay = rate_limit_delay
        self._scholarly = None
        self._last_request_time = 0

    def _get_scholarly(self):
        """Lazy load scholarly library."""
        if self._scholarly is None:
            try:
                from scholarly import scholarly
                self._scholarly = scholarly
            except ImportError:
                logger.error("scholarly library not installed. Run: pip install scholarly")
                raise ImportError("scholarly library required for Google Scholar support")
        return self._scholarly

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
