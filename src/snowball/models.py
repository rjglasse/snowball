"""Data models for the Snowball SLR tool."""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class PaperStatus(str, Enum):
    """Status of a paper in the review process."""
    PENDING = "pending"
    INCLUDED = "included"
    EXCLUDED = "excluded"
    MAYBE = "maybe"


class PaperSource(str, Enum):
    """Source of the paper."""
    SEED = "seed"
    BACKWARD = "backward"  # Found in references
    FORWARD = "forward"    # Found in citations


class ExclusionType(str, Enum):
    """How a paper was excluded."""
    AUTO = "auto"      # Excluded by filter criteria
    MANUAL = "manual"  # Excluded by reviewer


class Author(BaseModel):
    """Author information."""
    name: str
    affiliations: Optional[List[str]] = None


class Venue(BaseModel):
    """Publication venue information."""
    name: Optional[str] = None
    type: Optional[str] = None  # journal, conference, workshop, etc.
    year: Optional[int] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None


class Paper(BaseModel):
    """Represents a scholarly paper."""
    # Identifiers
    id: str = Field(description="Internal UUID for this paper")
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    pmid: Optional[str] = None
    semantic_scholar_id: Optional[str] = None
    openalex_id: Optional[str] = None

    # Metadata
    title: str
    authors: List[Author] = []
    year: Optional[int] = None
    abstract: Optional[str] = None
    venue: Optional[Venue] = None

    # Metrics
    citation_count: Optional[int] = None
    influential_citation_count: Optional[int] = None

    # References
    references: List[str] = Field(default_factory=list, description="IDs of referenced papers")
    citations: List[str] = Field(default_factory=list, description="IDs of citing papers")

    # Review data
    status: PaperStatus = PaperStatus.PENDING
    source: PaperSource
    source_paper_ids: List[str] = Field(default_factory=list, description="IDs of papers that led to this discovery")
    snowball_iteration: int = Field(0, description="Iteration when discovered (0 for seeds)")
    exclusion_type: Optional[ExclusionType] = Field(None, description="How paper was excluded (auto/manual)")

    # Review notes
    notes: str = ""
    review_date: Optional[datetime] = None
    tags: List[str] = Field(default_factory=list)

    # File location
    pdf_path: Optional[str] = None

    # Reference availability (for manual PDF fallback workflow)
    references_unavailable: bool = Field(False, description="True if refs couldn't be fetched, needs PDF")

    # Observation tracking (how many times discovered across iterations)
    observation_count: int = Field(1, description="Number of times this paper was discovered")

    # Raw data from APIs
    raw_data: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        use_enum_values = True


class FilterCriteria(BaseModel):
    """Criteria for filtering papers."""
    min_year: Optional[int] = None
    max_year: Optional[int] = None
    min_citations: Optional[int] = None
    max_citations: Optional[int] = None
    keywords: List[str] = Field(default_factory=list)
    excluded_keywords: List[str] = Field(default_factory=list)
    venue_types: List[str] = Field(default_factory=list)  # journal, conference, etc.
    min_influential_citations: Optional[int] = None


class IterationStats(BaseModel):
    """Statistics for a single snowball iteration."""
    iteration: int
    timestamp: datetime = Field(default_factory=datetime.now)

    # Discovery stats (set during snowball)
    discovered: int = 0
    backward: int = 0
    forward: int = 0
    auto_excluded: int = 0
    for_review: int = 0

    # Review stats (updated as papers are reviewed)
    manual_included: int = 0
    manual_excluded: int = 0
    manual_maybe: int = 0
    reviewed: int = 0  # Total papers reviewed in this iteration


class ReviewProject(BaseModel):
    """Represents an SLR project."""
    name: str
    description: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    # Configuration
    filter_criteria: FilterCriteria = Field(default_factory=FilterCriteria)

    # Seeds
    seed_paper_ids: List[str] = Field(default_factory=list)

    # Statistics
    total_papers: int = 0
    papers_by_status: Dict[str, int] = Field(default_factory=dict)
    current_iteration: int = 0

    # Iteration-level statistics for accountability
    iteration_stats: Dict[int, IterationStats] = Field(default_factory=dict)

    class Config:
        use_enum_values = True
