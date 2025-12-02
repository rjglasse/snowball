"""Shared utility functions for paper operations.

This module contains functions that are shared between the CLI and TUI interfaces
to avoid code duplication.
"""

from typing import Dict, List, Optional, Union
from .models import Paper, PaperStatus, PaperSource


# Status ordering for sorting
STATUS_ORDER: Dict[str, int] = {
    "pending": 0,
    "included": 1,
    "excluded": 2,
    "maybe": 3,
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
        status: Filter by status value (pending, included, excluded, maybe)
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
        column: Column name to sort by (Status, Title, Year, Citations, Source, Iter)

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

    elif column == "Citations":
        if paper.citation_count is None:
            return (1, 0)
        return (0, paper.citation_count)

    elif column == "Source":
        source_val = get_source_value(paper.source)
        return (0, SOURCE_ORDER.get(source_val, 999))

    elif column == "Iter":
        return (0, paper.snowball_iteration)

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
        "maybe": "#a371f7",
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
