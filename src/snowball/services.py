"""Reusable project lifecycle services for CLI and TUI workflows."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

from .apis.aggregator import APIAggregator
from .models import FilterCriteria, Paper, ReviewProject
from .paper_utils import title_similarity
from .parsers.pdf_parser import PDFParser
from .snowballing import SnowballEngine
from .storage.json_storage import JSONStorage


@dataclass
class ProjectContext:
    """Loaded project components."""

    project_dir: Path
    storage: JSONStorage
    project: ReviewProject
    engine: SnowballEngine
    extraction_method: str = "llm"


@dataclass
class SeedImportResult:
    """Result of a seed import operation."""

    added: list[Paper]
    skipped: list[str]


@dataclass
class SnowballRunResult:
    """Result of a guarded snowballing run."""

    stats: dict
    blocked_reason: str = ""

    @property
    def can_start(self) -> bool:
        return not self.blocked_reason


@dataclass
class PdfParseResult:
    """Result of parsing project PDFs and matching them to papers."""

    processed: int = 0
    no_match: int = 0
    failed: int = 0
    matched_files: list[Path] = field(default_factory=list)
    unmatched_files: list[Path] = field(default_factory=list)
    failed_files: list[Path] = field(default_factory=list)
    moved_files: list[tuple[Path, Path]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def create_project(
    directory: str | Path,
    name: Optional[str] = None,
    description: Optional[str] = None,
    min_year: Optional[int] = None,
    max_year: Optional[int] = None,
    research_question: Optional[str] = None,
) -> ProjectContext:
    """Create a new Snowball project and return loaded components."""
    project_dir = Path(directory)

    if project_dir.exists() and any(project_dir.iterdir()):
        raise ValueError(f"Directory {project_dir} already exists and is not empty")

    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "pdfs").mkdir(exist_ok=True)

    storage = JSONStorage(project_dir)
    project = ReviewProject(
        name=name or project_dir.name,
        description=description or "",
        research_question=research_question,
    )

    if min_year or max_year:
        project.filter_criteria = FilterCriteria(min_year=min_year, max_year=max_year)

    storage.save_project(project)
    engine = build_engine(storage)

    return ProjectContext(project_dir, storage, project, engine)


def load_project(
    directory: str | Path,
    *,
    s2_api_key: Optional[str] = None,
    email: Optional[str] = None,
    use_apis: Optional[list[str]] = None,
    scholar_proxy: Optional[str] = None,
    scholar_free_proxy: bool = False,
    extraction_method: str = "llm",
) -> ProjectContext:
    """Load an existing Snowball project and return loaded components."""
    project_dir = Path(directory)
    if not project_dir.exists():
        raise FileNotFoundError(f"Project directory {project_dir} does not exist")

    storage = JSONStorage(project_dir)
    project = storage.load_project()
    if not project:
        raise ValueError("No project found. Run 'snowball init' first.")

    engine = build_engine(
        storage,
        s2_api_key=s2_api_key,
        email=email,
        use_apis=use_apis,
        scholar_proxy=scholar_proxy,
        scholar_free_proxy=scholar_free_proxy,
        extraction_method=extraction_method,
    )
    return ProjectContext(project_dir, storage, project, engine, extraction_method)


def build_engine(
    storage: JSONStorage,
    *,
    s2_api_key: Optional[str] = None,
    email: Optional[str] = None,
    use_apis: Optional[list[str]] = None,
    scholar_proxy: Optional[str] = None,
    scholar_free_proxy: bool = False,
    extraction_method: str = "llm",
) -> SnowballEngine:
    """Build a Snowball engine with API and PDF parser configuration."""
    api = APIAggregator(
        s2_api_key=s2_api_key,
        email=email,
        use_apis=use_apis,
        scholar_proxy=scholar_proxy,
        scholar_free_proxy=scholar_free_proxy,
    )
    pdf_parser = PDFParser(extraction_method=extraction_method)
    return SnowballEngine(storage, api, pdf_parser)


def add_seed_pdfs(
    context: ProjectContext,
    pdf_paths: Sequence[str | Path],
) -> SeedImportResult:
    """Add seed papers from PDFs and copy them into the project pdfs directory."""
    pdfs_dir = context.project_dir / "pdfs"
    inbox_dir = pdfs_dir / "inbox"
    pdfs_dir.mkdir(exist_ok=True)
    inbox_dir.mkdir(exist_ok=True)

    added: list[Paper] = []
    skipped: list[str] = []

    for pdf_path in pdf_paths:
        pdf_file = Path(pdf_path)
        if not pdf_file.exists():
            skipped.append(f"PDF not found: {pdf_file}")
            continue

        paper = context.engine.add_seed_from_pdf(pdf_file, context.project)
        if not paper:
            inbox_path = copy_pdf_to_project(pdf_file, inbox_dir)
            skipped.append(f"Could not extract seed from PDF: {pdf_file}")
            skipped.append(f"Copied PDF to inbox for later parsing: {inbox_path}")
            continue

        dest_pdf = pdfs_dir / f"{paper.id}.pdf"
        shutil.copy2(pdf_file, dest_pdf)
        paper.pdf_path = str(dest_pdf)
        context.storage.save_paper(paper)
        added.append(paper)

    return SeedImportResult(added=added, skipped=skipped)


def run_snowball_iteration_checked(
    context: ProjectContext,
    *,
    direction: str = "both",
    force: bool = False,
) -> SnowballRunResult:
    """Run one snowball iteration after applying the review gate."""
    if not force:
        can_start, reason = context.engine.can_start_iteration(context.project)
        if not can_start:
            return SnowballRunResult(stats={}, blocked_reason=reason)

    stats = context.engine.run_snowball_iteration(context.project, direction=direction)
    context.project = context.storage.load_project() or context.project
    return SnowballRunResult(stats=stats)


def parse_project_pdfs(
    context: ProjectContext,
    *,
    extraction_method: Optional[str] = None,
) -> PdfParseResult:
    """Parse PDFs from pdfs/ and pdfs/inbox/, matching them to project papers."""
    pdfs_dir = context.project_dir / "pdfs"
    inbox_dir = pdfs_dir / "inbox"
    pdfs_dir.mkdir(exist_ok=True)
    inbox_dir.mkdir(exist_ok=True)

    pdf_files = sorted(inbox_dir.glob("*.pdf")) + sorted(pdfs_dir.glob("*.pdf"))
    result = PdfParseResult()
    if not pdf_files:
        result.warnings.append("No PDF files found in pdfs/ or pdfs/inbox/")
        return result

    papers = context.storage.load_all_papers()
    parser = PDFParser(extraction_method=extraction_method or context.extraction_method)

    for pdf_path in pdf_files:
        try:
            parsed = parser.parse(pdf_path)
        except Exception as exc:
            result.failed += 1
            result.failed_files.append(pdf_path)
            result.warnings.append(f"Failed to parse {pdf_path.name}: {exc}")
            continue

        if not parsed.title:
            result.failed += 1
            result.failed_files.append(pdf_path)
            result.warnings.append(f"Could not extract title from {pdf_path.name}")
            continue

        paper = find_paper_by_title_fuzzy(papers, parsed.title)
        if not paper:
            result.no_match += 1
            result.unmatched_files.append(pdf_path)
            continue

        final_path = pdf_path
        if pdf_path.parent == inbox_dir:
            final_path = _move_pdf_to_project(pdf_path, pdfs_dir)
            result.moved_files.append((pdf_path, final_path))

        if parsed.references:
            if paper.raw_data is None:
                paper.raw_data = {}
            paper.raw_data["grobid_references"] = parsed.references

        paper.pdf_path = str(final_path)
        context.storage.save_paper(paper)
        result.processed += 1
        result.matched_files.append(final_path)

    return result


def find_paper_by_title_fuzzy(
    papers: Sequence[Paper],
    title: str,
    threshold: float = 0.8,
) -> Optional[Paper]:
    """Find the best paper match for a parsed PDF title."""
    if not title:
        return None

    best_match: Optional[Paper] = None
    best_score = 0.0

    for paper in papers:
        if not paper.title:
            continue
        similarity = title_similarity(title, paper.title)
        if similarity >= threshold and similarity > best_score:
            best_score = similarity
            best_match = paper

    return best_match


def _move_pdf_to_project(pdf_file: Path, destination_dir: Path) -> Path:
    """Move a PDF to a project directory without overwriting existing files."""
    destination_dir.mkdir(parents=True, exist_ok=True)
    target = destination_dir / pdf_file.name

    if target.exists():
        stem = pdf_file.stem
        suffix = pdf_file.suffix or ".pdf"
        counter = 1
        while target.exists():
            target = destination_dir / f"{stem}-{counter}{suffix}"
            counter += 1

    shutil.move(str(pdf_file), str(target))
    return target


def copy_pdf_to_project(pdf_file: Path, destination_dir: Path) -> Path:
    """Copy a PDF to a project directory without overwriting existing files."""
    destination_dir.mkdir(parents=True, exist_ok=True)
    target = destination_dir / pdf_file.name

    if target.exists():
        stem = pdf_file.stem
        suffix = pdf_file.suffix or ".pdf"
        counter = 1
        while target.exists():
            target = destination_dir / f"{stem}-{counter}{suffix}"
            counter += 1

    shutil.copy2(pdf_file, target)
    return target


def add_seed_dois(
    context: ProjectContext,
    dois: Sequence[str],
) -> SeedImportResult:
    """Add seed papers from DOI strings."""
    added: list[Paper] = []
    skipped: list[str] = []

    for doi in dois:
        doi = doi.strip()
        if not doi:
            continue

        paper = context.engine.add_seed_from_doi(doi, context.project)
        if paper:
            added.append(paper)
        else:
            skipped.append(f"Could not find DOI: {doi}")

    return SeedImportResult(added=added, skipped=skipped)
