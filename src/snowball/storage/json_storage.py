"""JSON-based storage for papers and project data."""

import json
import uuid
import threading
import queue
import atexit
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict
from ..models import Paper, ReviewProject, PaperStatus
from ..paper_utils import papers_are_duplicates


class JSONStorage:
    """Handles persistence of papers and project metadata to JSON files.

    Uses write-behind caching for performance:
    - Reads come from in-memory cache (fast)
    - Writes update cache immediately, disk I/O happens in background thread
    """

    def __init__(self, project_dir: Path):
        """Initialize storage in the given directory.

        Args:
            project_dir: Directory to store project files
        """
        self.project_dir = Path(project_dir)
        self.project_dir.mkdir(parents=True, exist_ok=True)

        self.project_file = self.project_dir / "project.json"
        self.papers_file = self.project_dir / "papers.json"
        self.papers_dir = self.project_dir / "papers"
        self.papers_dir.mkdir(exist_ok=True)

        # In-memory cache for papers (paper_id -> Paper)
        self._papers_cache: Optional[Dict[str, Paper]] = None

        # Write-behind queue and thread
        self._write_queue: queue.Queue = queue.Queue()
        self._writer_thread: Optional[threading.Thread] = None
        self._shutdown_flag = threading.Event()
        self._start_writer_thread()

        # Register flush on exit to prevent data loss
        atexit.register(self.flush)

    def _start_writer_thread(self) -> None:
        """Start the background writer thread."""
        self._writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self._writer_thread.start()

    def _writer_loop(self) -> None:
        """Background thread that writes papers to disk."""
        while not self._shutdown_flag.is_set():
            try:
                # Wait for items with timeout to check shutdown flag periodically
                paper = self._write_queue.get(timeout=0.1)
                self._write_paper_to_disk(paper)
                self._write_queue.task_done()
            except queue.Empty:
                continue

    def _write_paper_to_disk(self, paper: Paper) -> None:
        """Actually write a paper to disk (called from background thread)."""
        paper_file = self.papers_dir / f"{paper.id}.json"
        with open(paper_file, 'w') as f:
            json.dump(paper.model_dump(mode='json'), f, indent=2, default=str)

    def flush(self) -> None:
        """Wait for all pending writes to complete.

        Call this before exiting to ensure no data is lost.
        """
        self._write_queue.join()

    def shutdown(self) -> None:
        """Shutdown the background writer thread cleanly."""
        self.flush()
        self._shutdown_flag.set()
        if self._writer_thread and self._writer_thread.is_alive():
            self._writer_thread.join(timeout=2.0)

    def save_project(self, project: ReviewProject) -> None:
        """Save project metadata."""
        project.updated_at = datetime.now()
        with open(self.project_file, 'w') as f:
            json.dump(project.model_dump(mode='json'), f, indent=2, default=str)

    def load_project(self) -> Optional[ReviewProject]:
        """Load project metadata."""
        if not self.project_file.exists():
            return None

        with open(self.project_file, 'r') as f:
            data = json.load(f)
            return ReviewProject.model_validate(data)

    def save_paper(self, paper: Paper) -> None:
        """Save a single paper using write-behind caching.

        Updates in-memory cache immediately (for fast UI response),
        then queues disk write for background thread.
        """
        # Update cache immediately (UI sees this right away)
        if self._papers_cache is not None:
            self._papers_cache[paper.id] = paper

        # Queue disk write for background thread
        self._write_queue.put(paper)

    def save_papers(self, papers: List[Paper]) -> None:
        """Save multiple papers."""
        for paper in papers:
            self.save_paper(paper)

        # Also save an index file for quick lookups
        self._update_papers_index(papers)

    def _update_papers_index(self, papers: List[Paper]) -> None:
        """Update the papers index file."""
        # Load existing index
        existing_papers = self.load_all_papers()
        papers_by_id = {p.id: p for p in existing_papers}

        # Update with new papers
        for paper in papers:
            papers_by_id[paper.id] = paper

        # Save index with key metadata for quick access
        index = {
            paper_id: {
                "title": paper.title,
                "year": paper.year,
                "status": paper.status,
                "source": paper.source,
                "doi": paper.doi,
                "citation_count": paper.citation_count,
            }
            for paper_id, paper in papers_by_id.items()
        }

        with open(self.papers_file, 'w') as f:
            json.dump(index, f, indent=2)

    def load_paper(self, paper_id: str) -> Optional[Paper]:
        """Load a single paper by ID."""
        # Check cache first
        if self._papers_cache is not None and paper_id in self._papers_cache:
            return self._papers_cache[paper_id]

        paper_file = self.papers_dir / f"{paper_id}.json"
        if not paper_file.exists():
            return None

        with open(paper_file, 'r') as f:
            data = json.load(f)
            paper = Paper.model_validate(data)

        # Update cache if it exists
        if self._papers_cache is not None:
            self._papers_cache[paper_id] = paper

        return paper

    def load_all_papers(self) -> List[Paper]:
        """Load all papers from individual files.

        Uses in-memory cache for performance. Papers are loaded from disk
        only on first call, then served from cache.
        """
        # Return cached papers if available
        if self._papers_cache is not None:
            return list(self._papers_cache.values())

        # Load from disk and populate cache
        self._papers_cache = {}
        for paper_file in self.papers_dir.glob("*.json"):
            with open(paper_file, 'r') as f:
                data = json.load(f)
                paper = Paper.model_validate(data)
                self._papers_cache[paper.id] = paper

        return list(self._papers_cache.values())

    def get_papers_by_status(self, status: PaperStatus) -> List[Paper]:
        """Get all papers with a specific status."""
        return [p for p in self.load_all_papers() if p.status == status]

    def get_papers_by_iteration(self, iteration: int) -> List[Paper]:
        """Get all papers from a specific snowball iteration."""
        return [p for p in self.load_all_papers() if p.snowball_iteration == iteration]

    def update_paper_status(self, paper_id: str, status: PaperStatus, notes: str = "") -> None:
        """Update a paper's review status."""
        paper = self.load_paper(paper_id)
        if paper:
            paper.status = status
            paper.notes = notes
            paper.review_date = datetime.now()
            self.save_paper(paper)

    def get_statistics(self) -> Dict:
        """Get statistics about the papers in the project."""
        papers = self.load_all_papers()

        stats = {
            "total": len(papers),
            "by_status": {},
            "by_iteration": {},
            "by_source": {},
        }

        for paper in papers:
            # Count by status
            status = paper.status.value if hasattr(paper.status, 'value') else paper.status
            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1

            # Count by iteration
            iter_key = str(paper.snowball_iteration)
            stats["by_iteration"][iter_key] = stats["by_iteration"].get(iter_key, 0) + 1

            # Count by source
            source = paper.source.value if hasattr(paper.source, 'value') else paper.source
            stats["by_source"][source] = stats["by_source"].get(source, 0) + 1

        return stats

    def find_paper_by_doi(self, doi: str) -> Optional[Paper]:
        """Find a paper by DOI."""
        for paper in self.load_all_papers():
            if paper.doi and paper.doi.lower() == doi.lower():
                return paper
        return None

    def find_paper_by_title(self, title: str) -> Optional[Paper]:
        """Find a paper by exact title match."""
        title_lower = title.lower()
        for paper in self.load_all_papers():
            if paper.title.lower() == title_lower:
                return paper
        return None

    def find_duplicate_paper(self, paper: Paper) -> Optional[Paper]:
        """Find a duplicate paper using fuzzy matching.

        Checks for duplicates by:
        - Exact DOI match, OR
        - Similar title AND similar authors

        Args:
            paper: Paper to check for duplicates

        Returns:
            Existing duplicate paper if found, None otherwise
        """
        for existing in self.load_all_papers():
            if papers_are_duplicates(paper, existing):
                return existing
        return None

    @staticmethod
    def generate_id() -> str:
        """Generate a unique ID for a paper."""
        return str(uuid.uuid4())

    def invalidate_cache(self) -> None:
        """Invalidate the papers cache.

        Call this if papers might have been modified externally
        (e.g., by another process or manual file editing).
        """
        self._papers_cache = None
