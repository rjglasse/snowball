"""Shared utility functions for paper operations.

This module contains functions that are shared between the CLI and TUI interfaces
to avoid code duplication.
"""

import logging
from typing import Dict, List, Optional, Union
from .models import Paper, PaperStatus, PaperSource

logger = logging.getLogger(__name__)


# Status ordering for sorting (pending first for review workflow)
STATUS_ORDER: Dict[str, int] = {
    "pending": 0,
    "included": 1,
    "excluded": 2,
}

# Source ordering for sorting
SOURCE_ORDER: Dict[str, int] = {
    "seed": 0,
    "backward": 1,
    "forward": 2,
}

# Maximum authors to display before truncation
MAX_AUTHORS_DISPLAY = 10

# Maximum title length before truncation
MAX_TITLE_LENGTH = 60


def get_status_value(status: Union[PaperStatus, str]) -> str:
    """Get string value from status (handles both enum and string).

    Args:
        status: Paper status as enum or string

    Returns:
        String representation of the status
    """
    return status.value if hasattr(status, "value") else status


def get_source_value(source: Union[PaperSource, str]) -> str:
    """Get string value from source (handles both enum and string).

    Args:
        source: Paper source as enum or string

    Returns:
        String representation of the source
    """
    return source.value if hasattr(source, "value") else source


def filter_papers(
    papers: List[Paper],
    status: Optional[str] = None,
    iteration: Optional[int] = None,
    source: Optional[str] = None,
) -> List[Paper]:
    """Filter papers by status, iteration, and/or source.

    Args:
        papers: List of papers to filter
        status: Filter by status value (pending, included, excluded)
        iteration: Filter by snowball iteration
        source: Filter by source value (seed, backward, forward)

    Returns:
        Filtered list of papers
    """
    result = papers

    if status:
        result = [p for p in result if get_status_value(p.status) == status]

    if iteration is not None:
        result = [p for p in result if p.snowball_iteration == iteration]

    if source:
        result = [p for p in result if get_source_value(p.source) == source]

    return result


def sort_papers(papers: List[Paper], sort_by: str, ascending: bool = True) -> List[Paper]:
    """Sort papers by the specified field.

    Args:
        papers: List of papers to sort
        sort_by: Field to sort by (citations, year, title, status)
        ascending: Sort in ascending order if True, descending if False

    Returns:
        Sorted list of papers
    """
    if sort_by == "citations":
        # None citations go to the end
        papers.sort(key=lambda p: (p.citation_count is None, -(p.citation_count or 0)))
    elif sort_by == "year":
        # None years go to the end
        papers.sort(key=lambda p: (p.year is None, -(p.year or 0)))
    elif sort_by == "title":
        papers.sort(key=lambda p: p.title.lower())
    elif sort_by == "status":
        papers.sort(key=lambda p: STATUS_ORDER.get(get_status_value(p.status), 999))

    if not ascending and sort_by in ("title", "status"):
        papers.reverse()

    return papers


def get_sort_key(paper: Paper, column: str):
    """Generate sort key for a paper based on column name.

    Returns a tuple where the first element controls None/missing value ordering,
    and the second element is the actual value for comparison.

    Args:
        paper: Paper to generate sort key for
        column: Column name to sort by (Status, Title, Year, Cite, Source, Iter, Obs)

    Returns:
        Tuple for sorting comparison
    """
    if column == "Status":
        status_val = get_status_value(paper.status)
        return (0, STATUS_ORDER.get(status_val, 999))

    elif column == "Title":
        return (0, paper.title.lower() if paper.title else "zzz")

    elif column == "Year":
        if paper.year is None:
            return (1, 0)  # (1, ...) puts None at end
        return (0, paper.year)

    elif column == "Cite":
        if paper.citation_count is None:
            return (1, 0)
        return (0, paper.citation_count)

    elif column == "Refs":
        # GROBID references count
        grobid_refs = paper.raw_data.get("grobid_references", []) if paper.raw_data else []
        if not grobid_refs:
            return (1, 0)  # No refs goes to end
        return (0, len(grobid_refs))

    elif column == "Source":
        source_val = get_source_value(paper.source)
        return (0, SOURCE_ORDER.get(source_val, 999))

    elif column == "Iter":
        return (0, paper.snowball_iteration)

    elif column == "Obs":
        return (0, paper.observation_count)

    else:
        # Fallback: sort by iteration, then status
        status_val = get_status_value(paper.status)
        return (0, (paper.snowball_iteration, status_val))


def format_authors(authors: list, max_display: int = MAX_AUTHORS_DISPLAY) -> str:
    """Format authors list for display.

    Args:
        authors: List of Author objects
        max_display: Maximum number of authors to show before truncation

    Returns:
        Formatted author string
    """
    if not authors:
        return ""

    author_names = [a.name for a in authors[:max_display]]
    result = ", ".join(author_names)

    if len(authors) > max_display:
        result += f" (+{len(authors) - max_display} more)"

    return result


def truncate_title(title: str, max_length: int = MAX_TITLE_LENGTH) -> str:
    """Truncate title for display.

    Args:
        title: Paper title
        max_length: Maximum length before truncation

    Returns:
        Truncated title with ellipsis if needed
    """
    if len(title) > max_length:
        return title[:max_length] + "..."
    return title


# Stopwords to ignore in title similarity comparison
TITLE_STOPWORDS = {'a', 'an', 'the', 'of', 'in', 'on', 'for', 'to', 'and', 'or', 'with', 'by', 'at', 'from'}


def title_similarity(title1: str, title2: str) -> float:
    """Calculate Jaccard similarity between two titles.

    Uses word-based Jaccard similarity with stopword removal.

    Args:
        title1: First title
        title2: Second title

    Returns:
        Similarity score between 0.0 and 1.0
    """
    if not title1 or not title2:
        return 0.0

    # Normalize and tokenize
    words1 = set(title1.lower().split()) - TITLE_STOPWORDS
    words2 = set(title2.lower().split()) - TITLE_STOPWORDS

    if not words1 or not words2:
        return 0.0

    intersection = len(words1 & words2)
    union = len(words1 | words2)

    return intersection / union if union > 0 else 0.0


def titles_match(title1: str, title2: str, threshold: float = 0.7) -> bool:
    """Check if two titles are similar enough to be considered the same paper.

    Args:
        title1: First title
        title2: Second title
        threshold: Minimum similarity score to consider a match (default 0.7)

    Returns:
        True if titles match above threshold
    """
    return title_similarity(title1, title2) >= threshold


def normalize_author_name(name: str) -> str:
    """Normalize author name for comparison.

    Extracts last name (assumed to be last word) and lowercases.
    Handles various formats like "John Smith", "J. Smith", "Smith, John".

    Args:
        name: Author name string

    Returns:
        Normalized name (lowercase last name)
    """
    if not name:
        return ""
    # Handle "Last, First" format
    if "," in name:
        name = name.split(",")[0].strip()
    else:
        # Get last word as surname
        parts = name.strip().split()
        name = parts[-1] if parts else ""
    return name.lower()


def authors_similarity(authors1: list, authors2: list) -> float:
    """Calculate similarity between two author lists.

    Compares normalized last names using Jaccard similarity.

    Args:
        authors1: First list of authors (Author objects or dicts with 'name')
        authors2: Second list of authors (Author objects or dicts with 'name')

    Returns:
        Similarity score between 0.0 and 1.0
    """
    if not authors1 or not authors2:
        return 0.0

    def get_name(author):
        if hasattr(author, 'name'):
            return author.name
        elif isinstance(author, dict):
            return author.get('name', '')
        return str(author)

    names1 = {normalize_author_name(get_name(a)) for a in authors1}
    names2 = {normalize_author_name(get_name(a)) for a in authors2}

    # Remove empty names
    names1 = {n for n in names1 if n}
    names2 = {n for n in names2 if n}

    if not names1 or not names2:
        return 0.0

    intersection = len(names1 & names2)
    union = len(names1 | names2)

    return intersection / union if union > 0 else 0.0


def papers_are_duplicates(
    paper1: Paper,
    paper2: Paper,
    title_threshold: float = 0.85,
    author_threshold: float = 0.3,
    year_tolerance: int = 1
) -> bool:
    """Check if two papers are likely duplicates (conservative approach).

    Papers are considered duplicates if:
    - They have the same DOI (exact match), OR
    - They have the same arXiv ID (exact match), OR
    - ALL of the following are true:
      - Their titles are similar (>= title_threshold, default 0.85)
      - Their years match (within year_tolerance, default ±1) OR one/both missing
      - Their authors are similar (>= author_threshold) OR one/both missing

    This conservative approach prioritizes forensic accuracy over convenience.
    False negatives (missing a duplicate) are preferable to false positives
    (wrongly merging distinct papers).

    Args:
        paper1: First paper
        paper2: Second paper
        title_threshold: Minimum title similarity (default 0.85 - stricter than before)
        author_threshold: Minimum author similarity (default 0.3)
        year_tolerance: Maximum year difference allowed (default 1 for preprint/published)

    Returns:
        True if papers are likely duplicates
    """
    # Exact DOI match is definitive
    if paper1.doi and paper2.doi:
        if paper1.doi.lower() == paper2.doi.lower():
            _log_duplicate_decision(paper1, paper2, "DOI match", 1.0, True)
            return True
        else:
            # Different DOIs = definitively NOT the same paper (forensic safety)
            _log_duplicate_decision(
                paper1, paper2,
                f"Different DOIs ({paper1.doi} vs {paper2.doi})",
                0.0, False
            )
            return False

    # Exact arXiv ID match is definitive
    if paper1.arxiv_id and paper2.arxiv_id:
        # Normalize arXiv IDs (remove version suffix like "v1", "v2")
        arxiv1 = paper1.arxiv_id.lower().split('v')[0].rstrip('.')
        arxiv2 = paper2.arxiv_id.lower().split('v')[0].rstrip('.')
        if arxiv1 == arxiv2:
            _log_duplicate_decision(paper1, paper2, "arXiv ID match", 1.0, True)
            return True
        else:
            # Different arXiv IDs = definitively NOT the same paper (forensic safety)
            _log_duplicate_decision(
                paper1, paper2,
                f"Different arXiv IDs ({paper1.arxiv_id} vs {paper2.arxiv_id})",
                0.0, False
            )
            return False

    # Check title similarity (required for fuzzy matching)
    if not paper1.title or not paper2.title:
        return False

    title_sim = title_similarity(paper1.title, paper2.title)
    if title_sim < title_threshold:
        # Only log near-misses for debugging
        if title_sim >= 0.6:
            _log_duplicate_decision(
                paper1, paper2,
                f"Title below threshold ({title_sim:.2f} < {title_threshold})",
                title_sim, False
            )
        return False

    # Check year compatibility (if both have years)
    if paper1.year and paper2.year:
        year_diff = abs(paper1.year - paper2.year)
        if year_diff > year_tolerance:
            _log_duplicate_decision(
                paper1, paper2,
                f"Year mismatch ({paper1.year} vs {paper2.year}, diff={year_diff})",
                title_sim, False
            )
            return False

    # Check author similarity (if both have authors)
    if paper1.authors and paper2.authors:
        author_sim = authors_similarity(paper1.authors, paper2.authors)
        if author_sim < author_threshold:
            _log_duplicate_decision(
                paper1, paper2,
                f"Authors below threshold ({author_sim:.2f} < {author_threshold})",
                title_sim, False
            )
            return False

    # All checks passed - this is a duplicate
    _log_duplicate_decision(
        paper1, paper2,
        f"Fuzzy match (title={title_sim:.2f})",
        title_sim, True
    )
    return True


def _log_duplicate_decision(
    paper1: Paper,
    paper2: Paper,
    reason: str,
    similarity: float,
    is_duplicate: bool
) -> None:
    """Log a duplicate detection decision for forensic auditing.

    Args:
        paper1: First paper
        paper2: Second paper
        reason: Explanation of the decision
        similarity: Similarity score
        is_duplicate: Whether papers were marked as duplicates
    """
    decision = "DUPLICATE" if is_duplicate else "DISTINCT"
    logger.debug(
        f"Dedup {decision}: {reason}\n"
        f"  Paper 1: [{paper1.year or '?'}] {paper1.title[:60]}...\n"
        f"  Paper 2: [{paper2.year or '?'}] {paper2.title[:60]}..."
    )


def paper_to_dict(paper: Paper, include_abstract: bool = False) -> dict:
    """Convert paper to dictionary for JSON output.

    Args:
        paper: Paper object to convert
        include_abstract: Include abstract in output (for detailed view)

    Returns:
        Dictionary representation of the paper
    """
    result = {
        "id": paper.id,
        "title": paper.title,
        "year": paper.year,
        "status": get_status_value(paper.status),
        "source": get_source_value(paper.source),
        "iteration": paper.snowball_iteration,
        "citations": paper.citation_count,
        "doi": paper.doi,
        "arxiv_id": paper.arxiv_id,
    }

    if include_abstract:
        result.update(
            {
                "authors": [a.name for a in paper.authors] if paper.authors else [],
                "abstract": paper.abstract,
                "influential_citations": paper.influential_citation_count,
                "venue": paper.venue.name if paper.venue else None,
                "notes": paper.notes,
                "tags": paper.tags,
            }
        )

    return result


def format_paper_text(paper: Paper) -> str:
    """Format paper details for text output (CLI).

    Args:
        paper: Paper to format

    Returns:
        Formatted text representation
    """
    lines = []
    lines.append(f"\n{'=' * 80}")
    lines.append(f"Title: {paper.title}")
    lines.append(f"{'=' * 80}")
    lines.append(f"ID:       {paper.id}")
    lines.append(f"Status:   {get_status_value(paper.status)}")
    lines.append(
        f"Source:   {get_source_value(paper.source)} (iteration {paper.snowball_iteration})"
    )
    lines.append("")

    if paper.authors:
        lines.append(f"Authors:  {format_authors(paper.authors)}")

    if paper.year:
        lines.append(f"Year:     {paper.year}")

    if paper.venue and paper.venue.name:
        lines.append(f"Venue:    {paper.venue.name}")

    if paper.doi:
        lines.append(f"DOI:      {paper.doi}")

    if paper.arxiv_id:
        lines.append(f"arXiv:    {paper.arxiv_id}")

    if paper.citation_count is not None:
        cit_text = str(paper.citation_count)
        if paper.influential_citation_count:
            cit_text += f" (influential: {paper.influential_citation_count})"
        lines.append(f"Citations: {cit_text}")

    if paper.abstract:
        lines.append(f"\nAbstract:\n{paper.abstract}")

    if paper.notes:
        lines.append(f"\nNotes:\n{paper.notes}")

    if paper.tags:
        lines.append(f"\nTags: {', '.join(paper.tags)}")

    lines.append("")
    return "\n".join(lines)


def format_paper_rich(paper: Paper) -> str:
    """Format paper details as rich text for TUI.

    Args:
        paper: Paper to format

    Returns:
        Rich text formatted string
    """
    lines = []
    lines.append(f"[bold #58a6ff]{paper.title}[/bold #58a6ff]\n")

    # Authors
    if paper.authors:
        lines.append(f"[bold #79c0ff]Authors:[/bold #79c0ff] {format_authors(paper.authors)}")

    # Year and venue
    year_venue = []
    if paper.year:
        year_venue.append(str(paper.year))
    if paper.venue and paper.venue.name:
        year_venue.append(paper.venue.name)
    if year_venue:
        lines.append(f"[bold #79c0ff]Published:[/bold #79c0ff] {' - '.join(year_venue)}")

    # Identifiers
    ids = []
    if paper.doi:
        ids.append(f"DOI: {paper.doi}")
    if paper.arxiv_id:
        ids.append(f"arXiv: {paper.arxiv_id}")
    if ids:
        lines.append(f"[bold #79c0ff]IDs:[/bold #79c0ff] {', '.join(ids)}")

    # Metrics
    if paper.citation_count is not None:
        cit_text = f"Citations: {paper.citation_count}"
        if paper.influential_citation_count:
            cit_text += f" (influential: {paper.influential_citation_count})"
        lines.append(f"[bold #79c0ff]Impact:[/bold #79c0ff] {cit_text}")

    # Review info
    status_colors = {
        "included": "#3fb950",
        "excluded": "#f85149",
        "pending": "#d29922",
    }
    status_val = get_status_value(paper.status)
    status_color = status_colors.get(status_val, "#c9d1d9")

    lines.append(
        f"[bold #79c0ff]Status:[/bold #79c0ff] [{status_color}]{status_val}[/{status_color}]"
    )
    lines.append(
        f"[bold #79c0ff]Source:[/bold #79c0ff] {get_source_value(paper.source)} "
        f"(iteration {paper.snowball_iteration})"
    )

    # Abstract
    if paper.abstract:
        lines.append("\n[bold #79c0ff]Abstract:[/bold #79c0ff]")
        lines.append(paper.abstract)

    # Notes
    if paper.notes:
        lines.append("\n[bold #79c0ff]Notes:[/bold #79c0ff]")
        lines.append(paper.notes)

    return "\n".join(lines)
