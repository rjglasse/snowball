"""Command-line interface for Snowball SLR tool."""

import os
import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Annotated
from enum import Enum

import typer

from .models import ReviewProject, FilterCriteria, PaperStatus
from .storage.json_storage import JSONStorage
from .apis.aggregator import APIAggregator
from .parsers.pdf_parser import PDFParser
from .snowballing import SnowballEngine
from .tui.app import run_tui
from .exporters.bibtex import BibTeXExporter
from .exporters.csv_exporter import CSVExporter
from .exporters.tikz import TikZExporter
from .paper_utils import (
    get_status_value,
    filter_papers,
    sort_papers,
    paper_to_dict,
    format_paper_text,
    truncate_title,
)


# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Create Typer app
app = typer.Typer(help="Snowball - Systematic Literature Review using Snowballing")


# Define enums for choice parameters
class ExportFormat(str, Enum):
    bibtex = "bibtex"
    csv = "csv"
    tikz = "tikz"
    png = "png"
    all = "all"


class SnowballDirection(str, Enum):
    backward = "backward"
    forward = "forward"
    both = "both"


class PaperStatusChoice(str, Enum):
    pending = "pending"
    included = "included"
    excluded = "excluded"


class PaperSourceChoice(str, Enum):
    seed = "seed"
    backward = "backward"
    forward = "forward"


class SortChoice(str, Enum):
    citations = "citations"
    year = "year"
    title = "title"
    status = "status"


class OutputFormat(str, Enum):
    table = "table"
    json = "json"


class TextOrJsonFormat(str, Enum):
    text = "text"
    json = "json"


class ScoringMethod(str, Enum):
    tfidf = "tfidf"
    llm = "llm"


def get_api_config(
    s2_api_key: Optional[str] = None,
    email: Optional[str] = None,
    use_scholar: bool = False,
    scholar_proxy: Optional[str] = None,
    scholar_free_proxy: bool = False,
) -> dict:
    """Get API configuration from arguments or environment variables.

    Environment variables:
        SEMANTIC_SCHOLAR_API_KEY: Semantic Scholar API key
        SNOWBALL_EMAIL: Email for API polite pools

    Returns:
        Dict with keys: s2_api_key, email, use_apis, scholar_proxy, scholar_free_proxy
    """
    s2_api_key = s2_api_key or os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
    email = email or os.environ.get("SNOWBALL_EMAIL")

    # Build API list - google_scholar only if explicitly enabled
    use_apis = ["semantic_scholar", "crossref", "openalex", "arxiv"]
    if use_scholar:
        use_apis.append("google_scholar")

    return {
        "s2_api_key": s2_api_key,
        "email": email,
        "use_apis": use_apis,
        "scholar_proxy": scholar_proxy,
        "scholar_free_proxy": scholar_free_proxy,
    }


@app.command()
def init(
    directory: Annotated[str, typer.Argument(help="Project directory")],
    name: Annotated[Optional[str], typer.Option(help="Project name")] = None,
    description: Annotated[Optional[str], typer.Option(help="Project description")] = None,
    min_year: Annotated[Optional[int], typer.Option(help="Minimum publication year")] = None,
    max_year: Annotated[Optional[int], typer.Option(help="Maximum publication year")] = None,
    research_question: Annotated[
        Optional[str], typer.Option("--research-question", "-rq", help="Research question for relevance scoring")
    ] = None,
) -> None:
    """Initialize a new SLR project."""
    project_dir = Path(directory)

    if project_dir.exists() and any(project_dir.iterdir()):
        logger.error(f"Directory {project_dir} already exists and is not empty")
        raise typer.Exit(1)

    project_dir.mkdir(parents=True, exist_ok=True)

    # Create pdfs folder for manual PDF imports
    (project_dir / "pdfs").mkdir(exist_ok=True)

    # Create storage
    storage = JSONStorage(project_dir)

    # Create project
    project = ReviewProject(
        name=name or project_dir.name,
        description=description or "",
        research_question=research_question,
    )

    # Set up filters if provided
    if min_year or max_year:
        project.filter_criteria = FilterCriteria(min_year=min_year, max_year=max_year)

    # Save project
    storage.save_project(project)

    logger.info(f"Initialized project '{project.name}' in {project_dir}")


@app.command("add-seed")
def add_seed(
    directory: Annotated[str, typer.Argument(help="Project directory")],
    pdf: Annotated[Optional[List[str]], typer.Option(help="Path(s) to seed PDF file(s)")] = None,
    doi: Annotated[Optional[List[str]], typer.Option(help="DOI(s) of seed paper(s)")] = None,
    s2_api_key: Annotated[Optional[str], typer.Option(help="Semantic Scholar API key")] = None,
    email: Annotated[Optional[str], typer.Option(help="Email for API polite pools")] = None,
    no_grobid: Annotated[bool, typer.Option(help="Don't use GROBID for PDF parsing")] = False,
    use_scholar: Annotated[
        bool,
        typer.Option(help="Enable Google Scholar API (disabled by default due to rate limiting)"),
    ] = False,
    scholar_proxy: Annotated[
        Optional[str],
        typer.Option(help="Proxy URL for Google Scholar (e.g., http://user:pass@host:port)"),
    ] = None,
    scholar_free_proxy: Annotated[
        bool,
        typer.Option(help="Use free rotating proxies for Google Scholar (requires free-proxy package)"),
    ] = False,
) -> None:
    """Add seed paper(s) to the project."""
    project_dir = Path(directory)

    if not project_dir.exists():
        logger.error(f"Project directory {project_dir} does not exist")
        raise typer.Exit(1)

    # Load project
    storage = JSONStorage(project_dir)
    project = storage.load_project()

    if not project:
        logger.error("No project found. Run 'snowball init' first.")
        raise typer.Exit(1)

    # Set up API and engine
    api_config = get_api_config(s2_api_key, email, use_scholar, scholar_proxy, scholar_free_proxy)
    api = APIAggregator(**api_config)
    pdf_parser = PDFParser(use_grobid=not no_grobid)
    engine = SnowballEngine(storage, api, pdf_parser)

    # Add seeds
    added_count = 0

    if pdf:
        import shutil

        pdfs_dir = project_dir / "pdfs"
        pdfs_dir.mkdir(exist_ok=True)

        for pdf_path in pdf:
            pdf_file = Path(pdf_path)
            if not pdf_file.exists():
                logger.warning(f"PDF not found: {pdf_file}")
                continue

            paper = engine.add_seed_from_pdf(pdf_file, project)
            if paper:
                # Copy PDF to project's pdfs folder
                dest_pdf = pdfs_dir / f"{paper.id}.pdf"
                shutil.copy2(pdf_file, dest_pdf)
                paper.pdf_path = str(dest_pdf)
                storage.save_paper(paper)
                logger.info(f"Added seed: {paper.title}")
                logger.info(f"  PDF copied to: {dest_pdf}")
                added_count += 1

    if doi:
        for doi_str in doi:
            paper = engine.add_seed_from_doi(doi_str, project)
            if paper:
                logger.info(f"Added seed: {paper.title}")
                added_count += 1

    logger.info(f"Added {added_count} seed paper(s)")


@app.command()
def snowball(
    directory: Annotated[str, typer.Argument(help="Project directory")],
    iterations: Annotated[Optional[int], typer.Option(help="Number of iterations to run")] = None,
    direction: Annotated[
        SnowballDirection,
        typer.Option(help="Snowballing direction: backward (references), forward (citations), or both (default)"),
    ] = SnowballDirection.both,
    s2_api_key: Annotated[Optional[str], typer.Option(help="Semantic Scholar API key")] = None,
    email: Annotated[Optional[str], typer.Option(help="Email for API polite pools")] = None,
    force: Annotated[
        bool,
        typer.Option(help="Force iteration even if there are unreviewed papers (not recommended)"),
    ] = False,
    use_scholar: Annotated[
        bool,
        typer.Option(help="Enable Google Scholar API (disabled by default due to rate limiting)"),
    ] = False,
    scholar_proxy: Annotated[
        Optional[str],
        typer.Option(help="Proxy URL for Google Scholar (e.g., http://user:pass@host:port)"),
    ] = None,
    scholar_free_proxy: Annotated[
        bool,
        typer.Option(help="Use free rotating proxies for Google Scholar (requires free-proxy package)"),
    ] = False,
) -> None:
    """Run snowballing iterations."""
    project_dir = Path(directory)

    if not project_dir.exists():
        logger.error(f"Project directory {project_dir} does not exist")
        raise typer.Exit(1)

    # Load project
    storage = JSONStorage(project_dir)
    project = storage.load_project()

    if not project:
        logger.error("No project found. Run 'snowball init' first.")
        raise typer.Exit(1)

    # Set up API and engine
    api_config = get_api_config(s2_api_key, email, use_scholar, scholar_proxy, scholar_free_proxy)
    api = APIAggregator(**api_config)
    engine = SnowballEngine(storage, api)

    # Check if we can start (unless --force is used)
    if not force:
        can_start, reason = engine.can_start_iteration(project)
        if not can_start:
            logger.error(reason)
            logger.info("Use --force to bypass this check (not recommended)")
            raise typer.Exit(1)

    # Run iterations
    iteration_count = 0
    while engine.should_continue_snowballing(project):
        # Check before each iteration (unless forcing)
        if not force and iteration_count > 0:
            can_start, reason = engine.can_start_iteration(project)
            if not can_start:
                logger.warning(reason)
                break

        logger.info(f"\nRunning snowball iteration {project.current_iteration + 1}...")

        stats = engine.run_snowball_iteration(project, direction=direction.value)

        logger.info(f"Iteration {project.current_iteration} complete:")
        logger.info(f"  - Discovered: {stats['added']} papers")
        logger.info(f"  - Backward: {stats['backward']}")
        logger.info(f"  - Forward: {stats['forward']}")
        logger.info(f"  - Auto-excluded: {stats['auto_excluded']}")
        logger.info(f"  - For review: {stats['for_review']}")

        # Reload project
        project = storage.load_project()
        iteration_count += 1

        if iterations and iteration_count >= iterations:
            break

    logger.info(f"\nSnowballing complete. Ran {iteration_count} iteration(s).")

    # Show summary
    summary = storage.get_statistics()
    logger.info("\nProject summary:")
    logger.info(f"  Total papers: {summary['total']}")
    logger.info(f"  By status: {summary['by_status']}")


@app.command()
def review(
    directory: Annotated[str, typer.Argument(help="Project directory")],
    s2_api_key: Annotated[Optional[str], typer.Option(help="Semantic Scholar API key")] = None,
    email: Annotated[Optional[str], typer.Option(help="Email for API polite pools")] = None,
    use_scholar: Annotated[
        bool,
        typer.Option(help="Enable Google Scholar API (disabled by default due to rate limiting)"),
    ] = False,
    scholar_proxy: Annotated[
        Optional[str],
        typer.Option(help="Proxy URL for Google Scholar (e.g., http://user:pass@host:port)"),
    ] = None,
    scholar_free_proxy: Annotated[
        bool,
        typer.Option(help="Use free rotating proxies for Google Scholar (requires free-proxy package)"),
    ] = False,
) -> None:
    """Launch the interactive review interface."""
    project_dir = Path(directory)

    if not project_dir.exists():
        logger.error(f"Project directory {project_dir} does not exist")
        raise typer.Exit(1)

    # Load project
    storage = JSONStorage(project_dir)
    project = storage.load_project()

    if not project:
        logger.error("No project found. Run 'snowball init' first.")
        raise typer.Exit(1)

    # Set up API and engine
    api_config = get_api_config(s2_api_key, email, use_scholar, scholar_proxy, scholar_free_proxy)
    api = APIAggregator(**api_config)
    engine = SnowballEngine(storage, api)

    # Redirect logging to file to avoid corrupting TUI display
    # Each session gets its own timestamped log file
    logs_dir = project_dir / "logs"
    logs_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = logs_dir / f"session_{timestamp}.log"
    root_logger = logging.getLogger()

    # Remove existing handlers and add file handler
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    file_handler.setLevel(logging.INFO)
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)

    # Launch TUI
    run_tui(project_dir, storage, engine, project)


@app.command()
def export(
    directory: Annotated[str, typer.Argument(help="Project directory")],
    format: Annotated[ExportFormat, typer.Option(help="Export format")] = ExportFormat.all,
    output: Annotated[Optional[str], typer.Option(help="Output directory")] = None,
    included_only: Annotated[bool, typer.Option(help="Only export included papers")] = False,
    standalone: Annotated[
        bool, typer.Option(help="Generate standalone LaTeX document (for TikZ)")
    ] = False,
) -> None:
    """Export results to various formats."""
    project_dir = Path(directory)

    if not project_dir.exists():
        logger.error(f"Project directory {project_dir} does not exist")
        raise typer.Exit(1)

    # Load project and papers
    storage = JSONStorage(project_dir)
    project = storage.load_project()

    if not project:
        logger.error("No project found.")
        raise typer.Exit(1)

    papers = storage.load_all_papers()

    if not papers:
        logger.warning("No papers to export")
        return

    # Default to output/ subfolder for tidy organization
    if output:
        output_dir = Path(output)
    else:
        output_dir = project_dir / "output"
    output_dir.mkdir(exist_ok=True)

    # Export BibTeX
    if format in [ExportFormat.bibtex, ExportFormat.all]:
        bibtex_exporter = BibTeXExporter()

        if included_only:
            bibtex_content = bibtex_exporter.export(papers, only_included=True)
            bibtex_path = output_dir / "included_papers.bib"
        else:
            bibtex_content = bibtex_exporter.export(papers, only_included=False)
            bibtex_path = output_dir / "all_papers.bib"

        with open(bibtex_path, "w") as f:
            f.write(bibtex_content)

        logger.info(f"Exported BibTeX to {bibtex_path}")

    # Export CSV
    if format in [ExportFormat.csv, ExportFormat.all]:
        csv_exporter = CSVExporter()

        if included_only:
            csv_path = output_dir / "included_papers.csv"
            csv_exporter.export(papers, csv_path, only_included=True)
        else:
            csv_path = output_dir / "all_papers.csv"
            csv_exporter.export(papers, csv_path, only_included=False, include_all_fields=True)

        logger.info(f"Exported CSV to {csv_path}")

    # Export TikZ
    if format in [ExportFormat.tikz, ExportFormat.all]:
        tikz_exporter = TikZExporter()

        if included_only:
            tikz_content = tikz_exporter.export(
                papers, only_included=True, standalone=standalone
            )
            tikz_path = output_dir / "citation_graph_included.tex"
        else:
            tikz_content = tikz_exporter.export(
                papers, only_included=False, standalone=standalone
            )
            tikz_path = output_dir / "citation_graph_all.tex"

        with open(tikz_path, "w") as f:
            f.write(tikz_content)

        logger.info(f"Exported TikZ to {tikz_path}")

    # Export PNG graph
    if format in [ExportFormat.png, ExportFormat.all]:
        from .visualization import generate_citation_graph

        output_path = generate_citation_graph(
            papers=papers,
            output_dir=output_dir,
            title=project.name,
            included_only=included_only,
        )

        if output_path:
            logger.info(f"Exported PNG graph to {output_path}")
        else:
            logger.warning("Could not generate PNG graph (missing matplotlib/networkx?)")


@app.command("list")
def list_papers(
    directory: Annotated[str, typer.Argument(help="Project directory")],
    status: Annotated[
        Optional[PaperStatusChoice], typer.Option(help="Filter by status")
    ] = None,
    iteration: Annotated[Optional[int], typer.Option(help="Filter by snowball iteration")] = None,
    source: Annotated[
        Optional[PaperSourceChoice], typer.Option(help="Filter by source")
    ] = None,
    sort: Annotated[
        SortChoice, typer.Option(help="Sort order (default: citations)")
    ] = SortChoice.citations,
    format: Annotated[
        OutputFormat, typer.Option(help="Output format (default: table)")
    ] = OutputFormat.table,
) -> None:
    """List papers in the project (non-interactive).

    This command provides a non-interactive way to view papers,
    suitable for AI agents and scripted workflows.
    """
    project_dir = Path(directory)

    if not project_dir.exists():
        logger.error(f"Project directory {project_dir} does not exist")
        raise typer.Exit(1)

    storage = JSONStorage(project_dir)
    project = storage.load_project()

    if not project:
        logger.error("No project found. Run 'snowball init' first.")
        raise typer.Exit(1)

    papers = storage.load_all_papers()

    # Filter papers using shared function
    papers = filter_papers(
        papers,
        status=status.value if status else None,
        iteration=iteration,
        source=source.value if source else None,
    )

    # Sort papers using shared function
    papers = sort_papers(papers, sort_by=sort.value, ascending=False)

    # Output format
    if format == OutputFormat.json:
        output = [paper_to_dict(paper) for paper in papers]
        print(json.dumps(output, indent=2))
    else:
        # Table format
        print(f"\n{'ID':<38} {'Status':<10} {'Year':<6} {'Citations':<10} {'Title'}")
        print("-" * 120)
        for paper in papers:
            status_str = get_status_value(paper.status)
            year = str(paper.year) if paper.year else "-"
            citations = str(paper.citation_count) if paper.citation_count is not None else "-"
            title = truncate_title(paper.title)
            print(f"{paper.id:<38} {status_str:<10} {year:<6} {citations:<10} {title}")

        print(f"\nTotal: {len(papers)} paper(s)")


@app.command()
def show(
    directory: Annotated[str, typer.Argument(help="Project directory")],
    id: Annotated[Optional[str], typer.Option(help="Paper ID")] = None,
    doi: Annotated[Optional[str], typer.Option(help="Paper DOI")] = None,
    title: Annotated[Optional[str], typer.Option(help="Paper title (exact or partial match)")] = None,
    format: Annotated[
        TextOrJsonFormat, typer.Option(help="Output format (default: text)")
    ] = TextOrJsonFormat.text,
) -> None:
    """Show details of a specific paper (non-interactive).

    This command provides a non-interactive way to view paper details,
    suitable for AI agents and scripted workflows.
    """
    project_dir = Path(directory)

    if not project_dir.exists():
        logger.error(f"Project directory {project_dir} does not exist")
        raise typer.Exit(1)

    storage = JSONStorage(project_dir)
    project = storage.load_project()

    if not project:
        logger.error("No project found. Run 'snowball init' first.")
        raise typer.Exit(1)

    # Find paper by ID, DOI, or title search
    paper = None
    if id:
        paper = storage.load_paper(id)
    elif doi:
        paper = storage.find_paper_by_doi(doi)
    elif title:
        paper = storage.find_paper_by_title(title)
        if not paper:
            # Try partial match
            papers = storage.load_all_papers()
            title_lower = title.lower()
            matches = [p for p in papers if title_lower in p.title.lower()]
            if len(matches) == 1:
                paper = matches[0]
            elif len(matches) > 1:
                logger.error(f"Multiple papers match '{title}':")
                for p in matches:
                    logger.error(f"  ID: {p.id} - {p.title}")
                logger.error("Please use --id to specify the exact paper.")
                raise typer.Exit(1)

    if not paper:
        logger.error("Paper not found")
        raise typer.Exit(1)

    # Output format
    if format == TextOrJsonFormat.json:
        output = paper_to_dict(paper, include_abstract=True)
        print(json.dumps(output, indent=2))
    else:
        # Human-readable format using shared function
        print(format_paper_text(paper))


@app.command("set-status")
def set_status(
    directory: Annotated[str, typer.Argument(help="Project directory")],
    status: Annotated[PaperStatusChoice, typer.Option(help="New status")],
    id: Annotated[Optional[str], typer.Option(help="Paper ID")] = None,
    doi: Annotated[Optional[str], typer.Option(help="Paper DOI")] = None,
    notes: Annotated[Optional[str], typer.Option(help="Review notes")] = None,
) -> None:
    """Set the status of a paper (non-interactive).

    This command provides a non-interactive way to update paper status,
    suitable for AI agents and scripted workflows.
    """
    project_dir = Path(directory)

    if not project_dir.exists():
        logger.error(f"Project directory {project_dir} does not exist")
        raise typer.Exit(1)

    storage = JSONStorage(project_dir)
    project = storage.load_project()

    if not project:
        logger.error("No project found. Run 'snowball init' first.")
        raise typer.Exit(1)

    # Find paper
    paper = None
    if id:
        paper = storage.load_paper(id)
    elif doi:
        paper = storage.find_paper_by_doi(doi)

    if not paper:
        logger.error("Paper not found")
        raise typer.Exit(1)

    # Map status string to enum
    status_map = {
        "pending": PaperStatus.PENDING,
        "included": PaperStatus.INCLUDED,
        "excluded": PaperStatus.EXCLUDED,
    }

    new_status = status_map.get(status.value)
    if not new_status:
        logger.error(f"Invalid status: {status.value}")
        raise typer.Exit(1)

    # Update paper
    old_status = get_status_value(paper.status)
    paper.status = new_status
    if notes:
        paper.notes = notes
    paper.review_date = datetime.now()

    storage.save_paper(paper)

    logger.info(f"Updated paper '{paper.title}'")
    logger.info(f"  Status: {old_status} -> {status.value}")
    if notes:
        logger.info(f"  Notes: {notes}")


@app.command()
def stats(
    directory: Annotated[str, typer.Argument(help="Project directory")],
    format: Annotated[
        TextOrJsonFormat, typer.Option(help="Output format (default: text)")
    ] = TextOrJsonFormat.text,
) -> None:
    """Show project statistics (non-interactive).

    This command provides a non-interactive way to view statistics,
    suitable for AI agents and scripted workflows. Includes detailed
    iteration stats for accountability.
    """
    project_dir = Path(directory)

    if not project_dir.exists():
        logger.error(f"Project directory {project_dir} does not exist")
        raise typer.Exit(1)

    storage = JSONStorage(project_dir)
    project = storage.load_project()

    if not project:
        logger.error("No project found. Run 'snowball init' first.")
        raise typer.Exit(1)

    statistics = storage.get_statistics()

    # Build iteration stats for output
    iteration_details = {}
    for iter_num, iter_stats in project.iteration_stats.items():
        iteration_details[str(iter_num)] = {
            "discovered": iter_stats.discovered,
            "backward": iter_stats.backward,
            "forward": iter_stats.forward,
            "auto_excluded": iter_stats.auto_excluded,
            "for_review": iter_stats.for_review,
            "manual_included": iter_stats.manual_included,
            "manual_excluded": iter_stats.manual_excluded,
            "reviewed": iter_stats.reviewed,
        }

    if format == TextOrJsonFormat.json:
        output = {
            "project_name": project.name,
            "current_iteration": project.current_iteration,
            "total_papers": statistics["total"],
            "by_status": statistics["by_status"],
            "by_iteration": statistics["by_iteration"],
            "by_source": statistics["by_source"],
            "seed_count": len(project.seed_paper_ids),
            "iteration_stats": iteration_details,
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"\n{'=' * 60}")
        print(f"Project: {project.name}")
        print(f"{'=' * 60}")
        print(f"Current iteration: {project.current_iteration}")
        print(f"Seed papers:       {len(project.seed_paper_ids)}")
        print(f"Total papers:      {statistics['total']}")
        print()

        # Overall status summary
        print("Overall Status:")
        for status_key, count in statistics["by_status"].items():
            print(f"  {status_key}: {count}")
        print()

        # Detailed iteration stats for accountability
        print("Iteration Details:")
        print("-" * 60)

        # Iteration 0 (seeds)
        seed_count = len(project.seed_paper_ids)
        if seed_count > 0:
            print(f"  Iteration 0 (seeds): {seed_count} papers")

        # Other iterations with full stats
        for iter_num in sorted(project.iteration_stats.keys()):
            iter_stats = project.iteration_stats[iter_num]
            print(f"\n  Iteration {iter_num}:")
            print(f"    Discovered:     {iter_stats.discovered} papers")
            print(f"      ├─ Backward:  {iter_stats.backward}")
            print(f"      └─ Forward:   {iter_stats.forward}")
            print(f"    Auto-excluded:  {iter_stats.auto_excluded}")
            print(f"    For review:     {iter_stats.for_review}")
            print(f"    Review progress:")
            print(f"      ├─ Reviewed:  {iter_stats.reviewed}/{iter_stats.for_review}")
            print(f"      ├─ Included:  {iter_stats.manual_included}")
            print(f"      └─ Excluded:  {iter_stats.manual_excluded}")

        print()
        print("By Source:")
        for source_key, count in statistics["by_source"].items():
            print(f"  {source_key}: {count}")
        print()


@app.command("update-citations")
def update_citations(
    directory: Annotated[str, typer.Argument(help="Project directory")],
    status: Annotated[
        Optional[PaperStatusChoice],
        typer.Option(help="Only update papers with this status"),
    ] = None,
    delay: Annotated[
        float,
        typer.Option(help="Delay between Google Scholar requests in seconds (default: 5.0)"),
    ] = 5.0,
) -> None:
    """Update citation counts from Google Scholar."""
    project_dir = Path(directory)

    if not project_dir.exists():
        logger.error(f"Project directory {project_dir} does not exist")
        raise typer.Exit(1)

    # Load project
    storage = JSONStorage(project_dir)
    project = storage.load_project()

    if not project:
        logger.error("No project found. Run 'snowball init' first.")
        raise typer.Exit(1)

    # Set up engine (no API needed for citation update)
    api = APIAggregator()
    engine = SnowballEngine(storage, api)

    # Get papers to update
    papers = None
    if status:
        status_map = {
            PaperStatusChoice.pending: PaperStatus.PENDING,
            PaperStatusChoice.included: PaperStatus.INCLUDED,
            PaperStatusChoice.excluded: PaperStatus.EXCLUDED,
        }
        papers = storage.get_papers_by_status(status_map[status])
        logger.info(f"Updating {len(papers)} papers with status '{status.value}'")

    # Run update
    stats_result = engine.update_citations_from_google_scholar(papers=papers, rate_limit_delay=delay)

    logger.info(f"\nUpdate complete:")
    logger.info(f"  Total papers: {stats_result['total']}")
    logger.info(f"  Updated: {stats_result['updated']}")
    logger.info(f"  Failed: {stats_result['failed']}")
    logger.info(f"  Skipped: {stats_result['skipped']}")


def _titles_match(title1: str, title2: str, threshold: float = 0.8) -> bool:
    """Check if two titles are similar enough to be the same paper.

    Uses Jaccard similarity on words after removing stopwords.
    """
    # Normalize titles
    words1 = set(title1.lower().split())
    words2 = set(title2.lower().split())

    # Remove common short words
    stopwords = {"a", "an", "the", "of", "in", "on", "for", "to", "and", "or", "with"}
    words1 = words1 - stopwords
    words2 = words2 - stopwords

    if not words1 or not words2:
        return False

    # Calculate Jaccard similarity
    intersection = len(words1 & words2)
    union = len(words1 | words2)
    similarity = intersection / union if union > 0 else 0

    return similarity >= threshold


def _find_paper_by_title_fuzzy(papers: list, title: str, threshold: float = 0.8):
    """Find a paper by fuzzy title match.

    Returns the best matching paper or None.
    """
    if not title:
        return None

    best_match = None
    best_score = 0

    for paper in papers:
        if not paper.title:
            continue

        # Calculate similarity
        words1 = set(title.lower().split())
        words2 = set(paper.title.lower().split())
        stopwords = {"a", "an", "the", "of", "in", "on", "for", "to", "and", "or", "with"}
        words1 = words1 - stopwords
        words2 = words2 - stopwords

        if not words1 or not words2:
            continue

        intersection = len(words1 & words2)
        union = len(words1 | words2)
        similarity = intersection / union if union > 0 else 0

        if similarity >= threshold and similarity > best_score:
            best_score = similarity
            best_match = paper

    return best_match


@app.command("parse-pdfs")
def parse_pdfs(
    directory: Annotated[str, typer.Argument(help="Project directory")],
) -> None:
    """Parse PDFs in the pdfs/ folder and attach references to matching papers."""
    project_dir = Path(directory)

    if not project_dir.exists():
        logger.error(f"Project directory {project_dir} does not exist")
        raise typer.Exit(1)

    # Load project
    storage = JSONStorage(project_dir)
    project = storage.load_project()

    if not project:
        logger.error("No project found. Run 'snowball init' first.")
        raise typer.Exit(1)

    # Check for pdfs directory
    pdfs_dir = project_dir / "pdfs"
    if not pdfs_dir.exists():
        logger.info(f"Creating pdfs directory: {pdfs_dir}")
        pdfs_dir.mkdir(parents=True, exist_ok=True)
        logger.info("No PDFs found. Add PDF files to this folder.")
        return

    # Find PDF files
    pdf_files = list(pdfs_dir.glob("*.pdf"))
    if not pdf_files:
        logger.info("No PDF files found in pdfs/ directory.")
        logger.info("Add PDF files to parse references.")
        return

    logger.info(f"Found {len(pdf_files)} PDF files")

    # Load all papers for title matching
    all_papers = storage.load_all_papers()
    logger.info(f"Loaded {len(all_papers)} papers for matching")

    # Initialize parser
    pdf_parser = PDFParser()
    if not pdf_parser.grobid_available:
        logger.warning("GROBID not available. Will use heuristic extraction (less accurate).")

    # Process each PDF
    processed = 0
    no_match = 0
    failed = 0

    for pdf_path in pdf_files:
        logger.info(f"Parsing: {pdf_path.name}")

        try:
            # Parse PDF to get title and references
            result = pdf_parser.parse(pdf_path)

            if not result.title:
                logger.warning(f"  Could not extract title from PDF")
                failed += 1
                continue

            logger.info(f"  Extracted title: {truncate_title(result.title, 60)}")

            # Find matching paper by title
            paper = _find_paper_by_title_fuzzy(all_papers, result.title)

            if not paper:
                logger.warning(f"  No matching paper found in project")
                no_match += 1
                continue

            logger.info(f"  Matched to: {truncate_title(paper.title, 60)}")

            # Store references
            if result.references:
                if paper.raw_data is None:
                    paper.raw_data = {}
                paper.raw_data["grobid_references"] = result.references
                logger.info(f"  Extracted {len(result.references)} references")
            else:
                logger.warning(f"  No references extracted from PDF")

            # Update paper
            paper.pdf_path = str(pdf_path)
            storage.save_paper(paper)

            processed += 1

        except Exception as e:
            logger.error(f"  Failed to parse {pdf_path.name}: {e}")
            failed += 1

    logger.info(f"\nParse complete:")
    logger.info(f"  Matched and processed: {processed}")
    logger.info(f"  No matching paper: {no_match}")
    logger.info(f"  Failed to parse: {failed}")

    if processed > 0:
        logger.info("\nReferences will be used in the next snowball iteration.")


@app.command("set-rq")
def set_research_question(
    directory: Annotated[str, typer.Argument(help="Project directory")],
    question: Annotated[str, typer.Argument(help="Research question text")],
) -> None:
    """Set or update the research question for a project."""
    project_dir = Path(directory)

    if not project_dir.exists():
        logger.error(f"Project directory {project_dir} does not exist")
        raise typer.Exit(1)

    storage = JSONStorage(project_dir)
    project = storage.load_project()

    if not project:
        logger.error("No project found. Run 'snowball init' first.")
        raise typer.Exit(1)

    project.research_question = question
    storage.save_project(project)

    logger.info(f"Research question set: {question}")


@app.command("compute-relevance")
def compute_relevance(
    directory: Annotated[str, typer.Argument(help="Project directory")],
    method: Annotated[
        ScoringMethod,
        typer.Option(
            help="Scoring method: tfidf (fast, offline) or llm (OpenAI API, requires OPENAI_API_KEY)"
        ),
    ] = ScoringMethod.tfidf,
    model: Annotated[
        str, typer.Option(help="LLM model to use (default: gpt-4o-mini)")
    ] = "gpt-4o-mini",
    status: Annotated[
        Optional[PaperStatusChoice],
        typer.Option(help="Only score papers with this status"),
    ] = None,
) -> None:
    """Compute relevance scores for papers against the research question."""
    project_dir = Path(directory)

    if not project_dir.exists():
        logger.error(f"Project directory {project_dir} does not exist")
        raise typer.Exit(1)

    storage = JSONStorage(project_dir)
    project = storage.load_project()

    if not project:
        logger.error("No project found. Run 'snowball init' first.")
        raise typer.Exit(1)

    if not project.research_question:
        logger.error("No research question set. Use 'snowball set-rq' or re-init with --research-question")
        raise typer.Exit(1)

    # Get papers to score
    papers = storage.load_all_papers()

    if status:
        status_map = {
            PaperStatusChoice.pending: PaperStatus.PENDING,
            PaperStatusChoice.included: PaperStatus.INCLUDED,
            PaperStatusChoice.excluded: PaperStatus.EXCLUDED,
        }
        papers = [p for p in papers if p.status == status_map[status]]

    if not papers:
        logger.info("No papers to score")
        return

    logger.info(f"Scoring {len(papers)} papers using {method.value.upper()} method...")

    # Get scorer
    from .scoring import get_scorer

    try:
        scorer_kwargs = {}
        if method == ScoringMethod.llm and model:
            scorer_kwargs["model"] = model
        scorer = get_scorer(method.value, **scorer_kwargs)
    except ImportError as e:
        logger.error(str(e))
        raise typer.Exit(1)
    except ValueError as e:
        logger.error(str(e))
        raise typer.Exit(1)

    # Progress callback
    def progress(current, total):
        if current % 10 == 0 or current == total:
            logger.info(f"Progress: {current}/{total}")

    # Score papers
    results = scorer.score_papers(project.research_question, papers, progress)

    # Save scores
    updated = 0
    for paper, score in results:
        paper.relevance_score = score
        storage.save_paper(paper)
        updated += 1

    storage.flush()
    logger.info(f"Updated relevance scores for {updated} papers")


def main():
    """Main CLI entry point."""
    app()


if __name__ == "__main__":
    main()
