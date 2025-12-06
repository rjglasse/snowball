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
        # Store GROBID-extracted references in raw_data for use in backward snowballing
        paper = Paper(
            id=JSONStorage.generate_id(),
            title=parse_result.title,
            authors=[{"name": name} for name in parse_result.authors],
            year=parse_result.year,
            abstract=parse_result.abstract,
            doi=parse_result.doi,
            source=PaperSource.SEED,
            snowball_iteration=0,
            pdf_path=str(pdf_path),
            raw_data={"grobid_references": parse_result.references}
        )

        logger.info(f"Extracted {len(parse_result.references)} references from PDF")

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
            # First iteration: use seed papers (skip excluded ones)
            all_seeds = [
                self.storage.load_paper(paper_id)
                for paper_id in project.seed_paper_ids
            ]
            source_papers = [p for p in all_seeds if p.status != PaperStatus.EXCLUDED]
        else:
            # Get papers from previous iteration that were included
            all_papers = self.storage.get_papers_by_iteration(current_iter)
            source_papers = [p for p in all_papers if p.status == PaperStatus.INCLUDED]

        if not source_papers:
            logger.warning(f"No source papers for iteration {next_iter}")
            return {"added": 0, "backward": 0, "forward": 0}

        logger.info(f"Processing {len(source_papers)} source papers")

        # Mark source papers as included (they're being used for snowballing)
        for paper in source_papers:
            if paper.status != PaperStatus.INCLUDED:
                paper.status = PaperStatus.INCLUDED
                self.storage.save_paper(paper)

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
                    references = self._get_references_for_paper(source_paper)
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

    def _get_references_for_paper(self, paper: Paper) -> List[Paper]:
        """Get references for a paper, preferring GROBID-extracted data over API.

        For papers parsed from PDF, we have the references already extracted by GROBID.
        We create Paper objects from this data, then enrich with API metadata.
        Falls back to API if no GROBID references are stored.

        Args:
            paper: Source paper to get references for

        Returns:
            List of Paper objects for each reference
        """
        # Check if we have GROBID-extracted references
        grobid_refs = paper.raw_data.get("grobid_references", []) if paper.raw_data else []

        if grobid_refs:
            logger.info(f"Using {len(grobid_refs)} GROBID-extracted references")
            references = []

            for ref in grobid_refs:
                if isinstance(ref, dict):
                    # Use title from GROBID if available, otherwise try raw text
                    title = ref.get("title")
                    if not title and ref.get("raw"):
                        # Extract title from raw text (text after year, before first period)
                        raw = ref["raw"]
                        if ref.get("year"):
                            year_str = str(ref["year"])
                            if year_str in raw:
                                parts = raw.split(year_str, 1)
                                if len(parts) > 1:
                                    title_part = parts[1].strip(". ")
                                    if ". " in title_part:
                                        title_part = title_part.split(". ")[0]
                                    if len(title_part) > 10:
                                        title = title_part
                    if not title:
                        title = ref.get("raw", "Unknown reference")[:200]

                    ref_paper = Paper(
                        id=JSONStorage.generate_id(),
                        title=title,
                        doi=ref.get("doi"),
                        year=ref.get("year"),
                        source=PaperSource.BACKWARD,
                        raw_data={"grobid_ref": ref}
                    )
                    references.append(ref_paper)

            logger.info(f"Created {len(references)} reference papers from GROBID data")

            # Enrich references with API metadata (citations, abstracts, etc.)
            logger.info("Enriching references with API metadata...")
            enriched_count = 0
            for ref_paper in references:
                try:
                    self.api.enrich_metadata(ref_paper)
                    if ref_paper.citation_count is not None or ref_paper.abstract:
                        enriched_count += 1
                except Exception as e:
                    logger.debug(f"Could not enrich {ref_paper.title[:50]}: {e}")

            logger.info(f"Enriched {enriched_count}/{len(references)} references with API metadata")
            return references

        # Fall back to API if no GROBID references
        logger.info("No GROBID references, falling back to API")
        return self.api.get_references(paper)

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
        # Check if there are papers to continue from
        if project.current_iteration == 0:
            return len(project.seed_paper_ids) > 0
        else:
            included_papers = [
                p for p in self.storage.get_papers_by_iteration(project.current_iteration)
                if p.status == PaperStatus.INCLUDED
            ]
            return len(included_papers) > 0

    def update_citations_from_google_scholar(
        self,
        papers: Optional[List[Paper]] = None,
        rate_limit_delay: float = 5.0
    ) -> dict:
        """Update citation counts for papers using Google Scholar.

        Args:
            papers: List of papers to update. If None, updates all papers.
            rate_limit_delay: Delay between Google Scholar requests (default 5s)

        Returns:
            Statistics about the update: {updated, failed, skipped}
        """
        from .apis.google_scholar import GoogleScholarClient

        gs_client = GoogleScholarClient(rate_limit_delay=rate_limit_delay)

        if papers is None:
            papers = self.storage.load_all_papers()

        stats = {"updated": 0, "failed": 0, "skipped": 0, "total": len(papers)}

        logger.info(f"Updating citations for {len(papers)} papers from Google Scholar...")

        for i, paper in enumerate(papers):
            if not paper.title or paper.title == "Unknown reference":
                stats["skipped"] += 1
                continue

            logger.info(f"[{i+1}/{len(papers)}] {paper.title[:50]}...")

            try:
                citation_count = gs_client.get_citation_count(paper.title)

                if citation_count is not None:
                    old_count = paper.citation_count
                    paper.citation_count = citation_count

                    # Store Google Scholar data in raw_data
                    if paper.raw_data is None:
                        paper.raw_data = {}
                    paper.raw_data["google_scholar_citations"] = citation_count

                    self.storage.save_paper(paper)
                    stats["updated"] += 1

                    if old_count != citation_count:
                        logger.info(f"  Updated: {old_count} -> {citation_count}")
                else:
                    stats["failed"] += 1
                    logger.debug(f"  Not found on Google Scholar")

            except Exception as e:
                stats["failed"] += 1
                logger.warning(f"  Error: {e}")

        logger.info(f"Citation update complete: {stats['updated']} updated, "
                   f"{stats['failed']} failed, {stats['skipped']} skipped")

        return stats
