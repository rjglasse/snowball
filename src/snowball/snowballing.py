"""Core snowballing logic."""

import logging
from pathlib import Path
from typing import List, Optional, Set
from .models import Paper, PaperSource, PaperStatus, ReviewProject
from .storage.json_storage import JSONStorage
from .apis.aggregator import APIAggregator
from .parsers.pdf_parser import PDFParser
from .filters.filter_engine import FilterEngine

logger = logging.getLogger(__name__)


class SnowballEngine:
    """Core engine for systematic literature review using snowballing."""

    def __init__(
        self,
        storage: JSONStorage,
        api_aggregator: APIAggregator,
        pdf_parser: Optional[PDFParser] = None
    ):
        """Initialize the snowball engine.

        Args:
            storage: JSON storage instance
            api_aggregator: API aggregator for fetching papers
            pdf_parser: PDF parser (optional, for seed PDFs)
        """
        self.storage = storage
        self.api = api_aggregator
        self.pdf_parser = pdf_parser or PDFParser()
        self.filter_engine = FilterEngine()

    def add_seed_from_pdf(self, pdf_path: Path, project: ReviewProject) -> Optional[Paper]:
        """Add a seed paper from a PDF file.

        Args:
            pdf_path: Path to PDF file
            project: Current review project

        Returns:
            Paper object if successful
        """
        logger.info(f"Parsing seed PDF: {pdf_path}")

        # Parse PDF
        parse_result = self.pdf_parser.parse(pdf_path)

        if not parse_result.title:
            logger.error("Could not extract title from PDF")
            return None

        # Create initial paper from parsed data
        paper = Paper(
            id=JSONStorage.generate_id(),
            title=parse_result.title,
            authors=[{"name": name} for name in parse_result.authors],
            year=parse_result.year,
            abstract=parse_result.abstract,
            doi=parse_result.doi,
            source=PaperSource.SEED,
            snowball_iteration=0,
            pdf_path=str(pdf_path)
        )

        # Try to identify and enrich the paper using APIs
        logger.info("Enriching paper metadata from APIs...")
        paper = self.api.identify_paper(paper)
        paper = self.api.enrich_metadata(paper)

        # Save the paper
        self.storage.save_paper(paper)

        # Update project
        if paper.id not in project.seed_paper_ids:
            project.seed_paper_ids.append(paper.id)
        self.storage.save_project(project)

        logger.info(f"Added seed paper: {paper.title}")
        return paper

    def add_seed_from_doi(self, doi: str, project: ReviewProject) -> Optional[Paper]:
        """Add a seed paper from a DOI.

        Args:
            doi: Digital Object Identifier
            project: Current review project

        Returns:
            Paper object if successful
        """
        logger.info(f"Searching for paper with DOI: {doi}")

        # Search for the paper
        paper = self.api.search_by_doi(doi)

        if not paper:
            logger.error(f"Could not find paper with DOI: {doi}")
            return None

        # Set as seed
        paper.source = PaperSource.SEED
        paper.snowball_iteration = 0

        # Save the paper
        self.storage.save_paper(paper)

        # Update project
        if paper.id not in project.seed_paper_ids:
            project.seed_paper_ids.append(paper.id)
        self.storage.save_project(project)

        logger.info(f"Added seed paper: {paper.title}")
        return paper

    def run_snowball_iteration(
        self, project: ReviewProject, direction: str = "both"
    ) -> dict:
        """Run one iteration of snowballing.

        Args:
            project: Current review project
            direction: Snowballing direction - "backward", "forward", or "both"

        Returns:
            Statistics about the iteration
        """
        current_iter = project.current_iteration
        next_iter = current_iter + 1

        logger.info(f"Starting snowball iteration {next_iter} (direction: {direction})")

        # Get papers from current iteration that are included
        if current_iter == 0:
            # First iteration: use seed papers
            source_papers = [
                self.storage.load_paper(paper_id)
                for paper_id in project.seed_paper_ids
            ]
        else:
            # Get papers from previous iteration that were included
            all_papers = self.storage.get_papers_by_iteration(current_iter)
            source_papers = [p for p in all_papers if p.status == PaperStatus.INCLUDED]

        if not source_papers:
            logger.warning(f"No source papers for iteration {next_iter}")
            return {"added": 0, "backward": 0, "forward": 0}

        logger.info(f"Processing {len(source_papers)} source papers")

        # Track discovered papers (using DOI/title to avoid duplicates)
        discovered_papers = []
        seen_identifiers: Set[str] = set()

        # Load existing papers to avoid duplicates
        existing_papers = self.storage.load_all_papers()
        for p in existing_papers:
            if p.doi:
                seen_identifiers.add(f"doi:{p.doi.lower()}")
            if p.title:
                seen_identifiers.add(f"title:{p.title.lower()}")

        backward_count = 0
        forward_count = 0

        # Process each source paper
        for source_paper in source_papers:
            logger.info(f"Processing: {source_paper.title}")

            # Backward snowballing (references)
            if direction in ("backward", "both"):
                try:
                    references = self.api.get_references(source_paper)
                    for ref_paper in references:
                        if self._is_new_paper(ref_paper, seen_identifiers):
                            ref_paper.source = PaperSource.BACKWARD
                            ref_paper.source_paper_id = source_paper.id
                            ref_paper.snowball_iteration = next_iter
                            discovered_papers.append(ref_paper)
                            self._mark_seen(ref_paper, seen_identifiers)
                            backward_count += 1
                except Exception as e:
                    logger.error(f"Error getting references: {e}")

            # Forward snowballing (citations)
            if direction in ("forward", "both"):
                try:
                    citations = self.api.get_citations(source_paper)
                    for cit_paper in citations:
                        if self._is_new_paper(cit_paper, seen_identifiers):
                            cit_paper.source = PaperSource.FORWARD
                            cit_paper.source_paper_id = source_paper.id
                            cit_paper.snowball_iteration = next_iter
                            discovered_papers.append(cit_paper)
                            self._mark_seen(cit_paper, seen_identifiers)
                            forward_count += 1
                except Exception as e:
                    logger.error(f"Error getting citations: {e}")

        logger.info(f"Discovered {len(discovered_papers)} new papers")
        logger.info(f"  Backward: {backward_count}, Forward: {forward_count}")

        # Apply filters
        filtered_papers = self.filter_engine.apply_filters(
            discovered_papers,
            project.filter_criteria
        )

        auto_excluded = len(discovered_papers) - len(filtered_papers)
        logger.info(f"Auto-excluded {auto_excluded} papers based on filters")

        # Mark auto-excluded papers
        for paper in discovered_papers:
            if paper not in filtered_papers:
                paper.status = PaperStatus.EXCLUDED
                paper.notes = "Auto-excluded by filters"

        # Save all discovered papers
        self.storage.save_papers(discovered_papers)

        # Update project
        project.current_iteration = next_iter
        self.storage.save_project(project)

        return {
            "added": len(discovered_papers),
            "backward": backward_count,
            "forward": forward_count,
            "auto_excluded": auto_excluded,
            "for_review": len(filtered_papers)
        }

    def _is_new_paper(self, paper: Paper, seen_identifiers: Set[str]) -> bool:
        """Check if a paper is new (not already seen)."""
        if paper.doi:
            if f"doi:{paper.doi.lower()}" in seen_identifiers:
                return False
        if paper.title:
            if f"title:{paper.title.lower()}" in seen_identifiers:
                return False
        return True

    def _mark_seen(self, paper: Paper, seen_identifiers: Set[str]) -> None:
        """Mark a paper as seen."""
        if paper.doi:
            seen_identifiers.add(f"doi:{paper.doi.lower()}")
        if paper.title:
            seen_identifiers.add(f"title:{paper.title.lower()}")

    def get_papers_for_review(self, iteration: Optional[int] = None) -> List[Paper]:
        """Get papers that need review.

        Args:
            iteration: Specific iteration to review (None for all pending)

        Returns:
            List of papers pending review
        """
        if iteration is not None:
            papers = self.storage.get_papers_by_iteration(iteration)
            return [p for p in papers if p.status == PaperStatus.PENDING]
        else:
            return self.storage.get_papers_by_status(PaperStatus.PENDING)

    def update_paper_review(
        self,
        paper_id: str,
        status: PaperStatus,
        notes: str = "",
        tags: Optional[List[str]] = None
    ) -> None:
        """Update a paper's review status.

        Args:
            paper_id: Paper ID
            status: New status
            notes: Review notes
            tags: Tags to add
        """
        paper = self.storage.load_paper(paper_id)
        if paper:
            paper.status = status
            paper.notes = notes
            if tags:
                paper.tags = tags
            self.storage.save_paper(paper)
            logger.info(f"Updated paper {paper.title}: {status}")

    def should_continue_snowballing(self, project: ReviewProject) -> bool:
        """Check if snowballing should continue.

        Args:
            project: Current review project

        Returns:
            True if more iterations should be run
        """
        # Check if max iterations reached
        if project.current_iteration >= project.max_iterations:
            return False

        # Check if there are papers to continue from
        if project.current_iteration == 0:
            return len(project.seed_paper_ids) > 0
        else:
            included_papers = [
                p for p in self.storage.get_papers_by_iteration(project.current_iteration)
                if p.status == PaperStatus.INCLUDED
            ]
            return len(included_papers) > 0
