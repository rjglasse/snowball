"""Command-line interface for Snowball SLR tool."""

import os
import sys
import logging
import json
from pathlib import Path
from datetime import datetime
import argparse

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


def get_api_config(args) -> dict:
    """Get API configuration from args or environment variables.

    Environment variables:
        SEMANTIC_SCHOLAR_API_KEY: Semantic Scholar API key
        SNOWBALL_EMAIL: Email for API polite pools

    Returns:
        Dict with keys: s2_api_key, email, use_apis, scholar_proxy, scholar_free_proxy
    """
    s2_api_key = getattr(args, "s2_api_key", None) or os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
    email = getattr(args, "email", None) or os.environ.get("SNOWBALL_EMAIL")

    # Build API list - google_scholar only if explicitly enabled
    use_apis = ["semantic_scholar", "crossref", "openalex", "arxiv"]
    if getattr(args, "use_scholar", False):
        use_apis.append("google_scholar")

    # Proxy settings for Google Scholar
    scholar_proxy = getattr(args, "scholar_proxy", None)
    scholar_free_proxy = getattr(args, "scholar_free_proxy", False)

    return {
        "s2_api_key": s2_api_key,
        "email": email,
        "use_apis": use_apis,
        "scholar_proxy": scholar_proxy,
        "scholar_free_proxy": scholar_free_proxy,
    }


def init_project(args) -> None:
    """Initialize a new SLR project."""
    project_dir = Path(args.directory)

    if project_dir.exists() and any(project_dir.iterdir()):
        logger.error(f"Directory {project_dir} already exists and is not empty")
        sys.exit(1)

    project_dir.mkdir(parents=True, exist_ok=True)

    # Create pdfs folder for manual PDF imports
    (project_dir / "pdfs").mkdir(exist_ok=True)

    # Create storage
    storage = JSONStorage(project_dir)

    # Create project
    project = ReviewProject(
        name=args.name or project_dir.name,
        description=args.description or "",
    )

    # Set up filters if provided
    if args.min_year or args.max_year:
        project.filter_criteria = FilterCriteria(min_year=args.min_year, max_year=args.max_year)

    # Save project
    storage.save_project(project)

    logger.info(f"Initialized project '{project.name}' in {project_dir}")


def add_seed(args) -> None:
    """Add seed paper(s) to the project."""
    project_dir = Path(args.directory)

    if not project_dir.exists():
        logger.error(f"Project directory {project_dir} does not exist")
        sys.exit(1)

    # Load project
    storage = JSONStorage(project_dir)
    project = storage.load_project()

    if not project:
        logger.error("No project found. Run 'snowball init' first.")
        sys.exit(1)

    # Set up API and engine
    api_config = get_api_config(args)
    api = APIAggregator(**api_config)
    pdf_parser = PDFParser(use_grobid=not args.no_grobid)
    engine = SnowballEngine(storage, api, pdf_parser)

    # Add seeds
    added_count = 0

    if args.pdf:
        import shutil

        pdfs_dir = project_dir / "pdfs"
        pdfs_dir.mkdir(exist_ok=True)

        for pdf_path in args.pdf:
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

    if args.doi:
        for doi in args.doi:
            paper = engine.add_seed_from_doi(doi, project)
            if paper:
                logger.info(f"Added seed: {paper.title}")
                added_count += 1

    logger.info(f"Added {added_count} seed paper(s)")


def run_snowball(args) -> None:
    """Run snowballing iterations."""
    project_dir = Path(args.directory)

    if not project_dir.exists():
        logger.error(f"Project directory {project_dir} does not exist")
        sys.exit(1)

    # Load project
    storage = JSONStorage(project_dir)
    project = storage.load_project()

    if not project:
        logger.error("No project found. Run 'snowball init' first.")
        sys.exit(1)

    # Set up API and engine
    api_config = get_api_config(args)
    api = APIAggregator(**api_config)
    engine = SnowballEngine(storage, api)

    # Check if we can start (unless --force is used)
    force = getattr(args, "force", False)
    if not force:
        can_start, reason = engine.can_start_iteration(project)
        if not can_start:
            logger.error(reason)
            logger.info("Use --force to bypass this check (not recommended)")
            sys.exit(1)

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

        stats = engine.run_snowball_iteration(project, direction=args.direction)

        logger.info(f"Iteration {project.current_iteration} complete:")
        logger.info(f"  - Discovered: {stats['added']} papers")
        logger.info(f"  - Backward: {stats['backward']}")
        logger.info(f"  - Forward: {stats['forward']}")
        logger.info(f"  - Auto-excluded: {stats['auto_excluded']}")
        logger.info(f"  - For review: {stats['for_review']}")

        # Reload project
        project = storage.load_project()
        iteration_count += 1

        if args.iterations and iteration_count >= args.iterations:
            break

    logger.info(f"\nSnowballing complete. Ran {iteration_count} iteration(s).")

    # Show summary
    summary = storage.get_statistics()
    logger.info("\nProject summary:")
    logger.info(f"  Total papers: {summary['total']}")
    logger.info(f"  By status: {summary['by_status']}")


def review(args) -> None:
    """Launch the interactive review interface."""
    project_dir = Path(args.directory)

    if not project_dir.exists():
        logger.error(f"Project directory {project_dir} does not exist")
        sys.exit(1)

    # Load project
    storage = JSONStorage(project_dir)
    project = storage.load_project()

    if not project:
        logger.error("No project found. Run 'snowball init' first.")
        sys.exit(1)

    # Set up API and engine
    api_config = get_api_config(args)
    api = APIAggregator(**api_config)
    engine = SnowballEngine(storage, api)

    # Redirect logging to file to avoid corrupting TUI display
    log_file = project_dir / "snowball.log"
    root_logger = logging.getLogger()

    # Remove existing handlers and add file handler
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    root_logger.addHandler(file_handler)

    # Launch TUI
    run_tui(project_dir, storage, engine, project)


def export_results(args) -> None:
    """Export results to various formats."""
    project_dir = Path(args.directory)

    if not project_dir.exists():
        logger.error(f"Project directory {project_dir} does not exist")
        sys.exit(1)

    # Load project and papers
    storage = JSONStorage(project_dir)
    project = storage.load_project()

    if not project:
        logger.error("No project found.")
        sys.exit(1)

    papers = storage.load_all_papers()

    if not papers:
        logger.warning("No papers to export")
        return

    output_dir = Path(args.output) if args.output else project_dir

    # Export BibTeX
    if args.format in ["bibtex", "all"]:
        bibtex_exporter = BibTeXExporter()

        if args.included_only:
            bibtex_content = bibtex_exporter.export(papers, only_included=True)
            bibtex_path = output_dir / "included_papers.bib"
        else:
            bibtex_content = bibtex_exporter.export(papers, only_included=False)
            bibtex_path = output_dir / "all_papers.bib"

        with open(bibtex_path, "w") as f:
            f.write(bibtex_content)

        logger.info(f"Exported BibTeX to {bibtex_path}")

    # Export CSV
    if args.format in ["csv", "all"]:
        csv_exporter = CSVExporter()

        if args.included_only:
            csv_path = output_dir / "included_papers.csv"
            csv_exporter.export(papers, csv_path, only_included=True)
        else:
            csv_path = output_dir / "all_papers.csv"
            csv_exporter.export(papers, csv_path, only_included=False, include_all_fields=True)

        logger.info(f"Exported CSV to {csv_path}")

    # Export TikZ
    if args.format in ["tikz", "all"]:
        tikz_exporter = TikZExporter()

        if args.included_only:
            tikz_content = tikz_exporter.export(
                papers, only_included=True, standalone=args.standalone
            )
            tikz_path = output_dir / "citation_graph_included.tex"
        else:
            tikz_content = tikz_exporter.export(
                papers, only_included=False, standalone=args.standalone
            )
            tikz_path = output_dir / "citation_graph_all.tex"

        with open(tikz_path, "w") as f:
            f.write(tikz_content)

        logger.info(f"Exported TikZ to {tikz_path}")


def list_papers(args) -> None:
    """List papers in the project (non-interactive).

    This command provides a non-interactive way to view papers,
    suitable for AI agents and scripted workflows.
    """
    project_dir = Path(args.directory)

    if not project_dir.exists():
        logger.error(f"Project directory {project_dir} does not exist")
        sys.exit(1)

    storage = JSONStorage(project_dir)
    project = storage.load_project()

    if not project:
        logger.error("No project found. Run 'snowball init' first.")
        sys.exit(1)

    papers = storage.load_all_papers()

    # Filter papers using shared function
    papers = filter_papers(papers, status=args.status, iteration=args.iteration, source=args.source)

    # Sort papers using shared function
    papers = sort_papers(papers, sort_by=args.sort, ascending=False)

    # Output format
    if args.format == "json":
        output = [paper_to_dict(paper) for paper in papers]
        print(json.dumps(output, indent=2))
    else:
        # Table format
        print(f"\n{'ID':<38} {'Status':<10} {'Year':<6} {'Citations':<10} {'Title'}")
        print("-" * 120)
        for paper in papers:
            status = get_status_value(paper.status)
            year = str(paper.year) if paper.year else "-"
            citations = str(paper.citation_count) if paper.citation_count is not None else "-"
            title = truncate_title(paper.title)
            print(f"{paper.id:<38} {status:<10} {year:<6} {citations:<10} {title}")

        print(f"\nTotal: {len(papers)} paper(s)")


def show_paper(args) -> None:
    """Show details of a specific paper (non-interactive).

    This command provides a non-interactive way to view paper details,
    suitable for AI agents and scripted workflows.
    """
    project_dir = Path(args.directory)

    if not project_dir.exists():
        logger.error(f"Project directory {project_dir} does not exist")
        sys.exit(1)

    storage = JSONStorage(project_dir)
    project = storage.load_project()

    if not project:
        logger.error("No project found. Run 'snowball init' first.")
        sys.exit(1)

    # Find paper by ID, DOI, or title search
    paper = None
    if args.id:
        paper = storage.load_paper(args.id)
    elif args.doi:
        paper = storage.find_paper_by_doi(args.doi)
    elif args.title:
        paper = storage.find_paper_by_title(args.title)
        if not paper:
            # Try partial match
            papers = storage.load_all_papers()
            title_lower = args.title.lower()
            matches = [p for p in papers if title_lower in p.title.lower()]
            if len(matches) == 1:
                paper = matches[0]
            elif len(matches) > 1:
                logger.error(f"Multiple papers match '{args.title}':")
                for p in matches:
                    logger.error(f"  ID: {p.id} - {p.title}")
                logger.error("Please use --id to specify the exact paper.")
                sys.exit(1)

    if not paper:
        logger.error("Paper not found")
        sys.exit(1)

    # Output format
    if args.format == "json":
        output = paper_to_dict(paper, include_abstract=True)
        print(json.dumps(output, indent=2))
    else:
        # Human-readable format using shared function
        print(format_paper_text(paper))


def set_status(args) -> None:
    """Set the status of a paper (non-interactive).

    This command provides a non-interactive way to update paper status,
    suitable for AI agents and scripted workflows.
    """
    project_dir = Path(args.directory)

    if not project_dir.exists():
        logger.error(f"Project directory {project_dir} does not exist")
        sys.exit(1)

    storage = JSONStorage(project_dir)
    project = storage.load_project()

    if not project:
        logger.error("No project found. Run 'snowball init' first.")
        sys.exit(1)

    # Find paper
    paper = None
    if args.id:
        paper = storage.load_paper(args.id)
    elif args.doi:
        paper = storage.find_paper_by_doi(args.doi)

    if not paper:
        logger.error("Paper not found")
        sys.exit(1)

    # Map status string to enum
    status_map = {
        "pending": PaperStatus.PENDING,
        "included": PaperStatus.INCLUDED,
        "excluded": PaperStatus.EXCLUDED,
    }

    new_status = status_map.get(args.status)
    if not new_status:
        logger.error(f"Invalid status: {args.status}")
        sys.exit(1)

    # Update paper
    old_status = get_status_value(paper.status)
    paper.status = new_status
    if args.notes:
        paper.notes = args.notes
    paper.review_date = datetime.now()

    storage.save_paper(paper)

    logger.info(f"Updated paper '{paper.title}'")
    logger.info(f"  Status: {old_status} -> {args.status}")
    if args.notes:
        logger.info(f"  Notes: {args.notes}")


def show_stats(args) -> None:
    """Show project statistics (non-interactive).

    This command provides a non-interactive way to view statistics,
    suitable for AI agents and scripted workflows. Includes detailed
    iteration stats for accountability.
    """
    project_dir = Path(args.directory)

    if not project_dir.exists():
        logger.error(f"Project directory {project_dir} does not exist")
        sys.exit(1)

    storage = JSONStorage(project_dir)
    project = storage.load_project()

    if not project:
        logger.error("No project found. Run 'snowball init' first.")
        sys.exit(1)

    stats = storage.get_statistics()

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

    if args.format == "json":
        output = {
            "project_name": project.name,
            "current_iteration": project.current_iteration,
            "total_papers": stats["total"],
            "by_status": stats["by_status"],
            "by_iteration": stats["by_iteration"],
            "by_source": stats["by_source"],
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
        print(f"Total papers:      {stats['total']}")
        print()

        # Overall status summary
        print("Overall Status:")
        for status, count in stats["by_status"].items():
            print(f"  {status}: {count}")
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
        for source, count in stats["by_source"].items():
            print(f"  {source}: {count}")
        print()


def update_citations(args) -> None:
    """Update citation counts from Google Scholar."""
    project_dir = Path(args.directory)

    if not project_dir.exists():
        logger.error(f"Project directory {project_dir} does not exist")
        sys.exit(1)

    # Load project
    storage = JSONStorage(project_dir)
    project = storage.load_project()

    if not project:
        logger.error("No project found. Run 'snowball init' first.")
        sys.exit(1)

    # Set up engine (no API needed for citation update)
    from .apis.aggregator import APIAggregator

    api = APIAggregator()
    engine = SnowballEngine(storage, api)

    # Get papers to update
    papers = None
    if args.status:
        status_map = {
            "pending": PaperStatus.PENDING,
            "included": PaperStatus.INCLUDED,
            "excluded": PaperStatus.EXCLUDED,
        }
        papers = storage.get_papers_by_status(status_map[args.status])
        logger.info(f"Updating {len(papers)} papers with status '{args.status}'")

    # Run update
    stats = engine.update_citations_from_google_scholar(papers=papers, rate_limit_delay=args.delay)

    logger.info(f"\nUpdate complete:")
    logger.info(f"  Total papers: {stats['total']}")
    logger.info(f"  Updated: {stats['updated']}")
    logger.info(f"  Failed: {stats['failed']}")
    logger.info(f"  Skipped: {stats['skipped']}")


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


def parse_pdfs(args) -> None:
    """Parse PDFs in the pdfs/ folder and attach references to matching papers."""
    project_dir = Path(args.directory)

    if not project_dir.exists():
        logger.error(f"Project directory {project_dir} does not exist")
        sys.exit(1)

    # Load project
    storage = JSONStorage(project_dir)
    project = storage.load_project()

    if not project:
        logger.error("No project found. Run 'snowball init' first.")
        sys.exit(1)

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


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Snowball - Systematic Literature Review using Snowballing"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Init command
    init_parser = subparsers.add_parser("init", help="Initialize a new SLR project")
    init_parser.add_argument("directory", help="Project directory")
    init_parser.add_argument("--name", help="Project name")
    init_parser.add_argument("--description", help="Project description")
    init_parser.add_argument("--min-year", type=int, help="Minimum publication year")
    init_parser.add_argument("--max-year", type=int, help="Maximum publication year")

    # Add seed command
    seed_parser = subparsers.add_parser("add-seed", help="Add seed paper(s)")
    seed_parser.add_argument("directory", help="Project directory")
    seed_parser.add_argument("--pdf", nargs="+", help="Path(s) to seed PDF file(s)")
    seed_parser.add_argument("--doi", nargs="+", help="DOI(s) of seed paper(s)")
    seed_parser.add_argument("--s2-api-key", help="Semantic Scholar API key")
    seed_parser.add_argument("--email", help="Email for API polite pools")
    seed_parser.add_argument(
        "--no-grobid", action="store_true", help="Don't use GROBID for PDF parsing"
    )
    seed_parser.add_argument(
        "--use-scholar", action="store_true",
        help="Enable Google Scholar API (disabled by default due to rate limiting)"
    )
    seed_parser.add_argument(
        "--scholar-proxy",
        help="Proxy URL for Google Scholar (e.g., http://user:pass@host:port)"
    )
    seed_parser.add_argument(
        "--scholar-free-proxy", action="store_true",
        help="Use free rotating proxies for Google Scholar (requires free-proxy package)"
    )

    # Snowball command
    snowball_parser = subparsers.add_parser("snowball", help="Run snowballing iterations")
    snowball_parser.add_argument("directory", help="Project directory")
    snowball_parser.add_argument("--iterations", type=int, help="Number of iterations to run")
    snowball_parser.add_argument(
        "--direction",
        choices=["backward", "forward", "both"],
        default="both",
        help="Snowballing direction: backward (references), forward (citations), or both (default)",
    )
    snowball_parser.add_argument("--s2-api-key", help="Semantic Scholar API key")
    snowball_parser.add_argument("--email", help="Email for API polite pools")
    snowball_parser.add_argument(
        "--force",
        action="store_true",
        help="Force iteration even if there are unreviewed papers (not recommended)",
    )
    snowball_parser.add_argument(
        "--use-scholar", action="store_true",
        help="Enable Google Scholar API (disabled by default due to rate limiting)"
    )
    snowball_parser.add_argument(
        "--scholar-proxy",
        help="Proxy URL for Google Scholar (e.g., http://user:pass@host:port)"
    )
    snowball_parser.add_argument(
        "--scholar-free-proxy", action="store_true",
        help="Use free rotating proxies for Google Scholar (requires free-proxy package)"
    )

    # Review command
    review_parser = subparsers.add_parser("review", help="Launch interactive review interface")
    review_parser.add_argument("directory", help="Project directory")
    review_parser.add_argument("--s2-api-key", help="Semantic Scholar API key")
    review_parser.add_argument("--email", help="Email for API polite pools")
    review_parser.add_argument(
        "--use-scholar", action="store_true",
        help="Enable Google Scholar API (disabled by default due to rate limiting)"
    )
    review_parser.add_argument(
        "--scholar-proxy",
        help="Proxy URL for Google Scholar (e.g., http://user:pass@host:port)"
    )
    review_parser.add_argument(
        "--scholar-free-proxy", action="store_true",
        help="Use free rotating proxies for Google Scholar (requires free-proxy package)"
    )

    # Export command
    export_parser = subparsers.add_parser("export", help="Export results")
    export_parser.add_argument("directory", help="Project directory")
    export_parser.add_argument(
        "--format", choices=["bibtex", "csv", "tikz", "all"], default="all", help="Export format"
    )
    export_parser.add_argument("--output", help="Output directory")
    export_parser.add_argument(
        "--included-only", action="store_true", help="Only export included papers"
    )
    export_parser.add_argument(
        "--standalone", action="store_true", help="Generate standalone LaTeX document (for TikZ)"
    )

    # List command (non-interactive)
    list_parser = subparsers.add_parser(
        "list", help="List papers non-interactively (for AI agents/scripts)"
    )
    list_parser.add_argument("directory", help="Project directory")
    list_parser.add_argument(
        "--status", choices=["pending", "included", "excluded"], help="Filter by status"
    )
    list_parser.add_argument("--iteration", type=int, help="Filter by snowball iteration")
    list_parser.add_argument(
        "--source", choices=["seed", "backward", "forward"], help="Filter by source"
    )
    list_parser.add_argument(
        "--sort",
        choices=["citations", "year", "title", "status"],
        default="citations",
        help="Sort order (default: citations)",
    )
    list_parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )

    # Show command (non-interactive)
    show_parser = subparsers.add_parser(
        "show", help="Show paper details non-interactively (for AI agents/scripts)"
    )
    show_parser.add_argument("directory", help="Project directory")
    show_parser.add_argument("--id", help="Paper ID")
    show_parser.add_argument("--doi", help="Paper DOI")
    show_parser.add_argument("--title", help="Paper title (exact or partial match)")
    show_parser.add_argument(
        "--format", choices=["text", "json"], default="text", help="Output format (default: text)"
    )

    # Set-status command (non-interactive)
    set_status_parser = subparsers.add_parser(
        "set-status", help="Set paper status non-interactively (for AI agents/scripts)"
    )
    set_status_parser.add_argument("directory", help="Project directory")
    set_status_parser.add_argument("--id", help="Paper ID")
    set_status_parser.add_argument("--doi", help="Paper DOI")
    set_status_parser.add_argument(
        "--status",
        required=True,
        choices=["pending", "included", "excluded"],
        help="New status",
    )
    set_status_parser.add_argument("--notes", help="Review notes")

    # Stats command (non-interactive)
    stats_parser = subparsers.add_parser(
        "stats", help="Show project statistics non-interactively (for AI agents/scripts)"
    )
    stats_parser.add_argument("directory", help="Project directory")
    stats_parser.add_argument(
        "--format", choices=["text", "json"], default="text", help="Output format (default: text)"
    )

    # Update citations command
    update_citations_parser = subparsers.add_parser(
        "update-citations", help="Update citation counts from Google Scholar"
    )
    update_citations_parser.add_argument("directory", help="Project directory")
    update_citations_parser.add_argument(
        "--status",
        choices=["pending", "included", "excluded"],
        help="Only update papers with this status",
    )
    update_citations_parser.add_argument(
        "--delay",
        type=float,
        default=5.0,
        help="Delay between Google Scholar requests in seconds (default: 5.0)",
    )

    # Parse PDFs command
    parse_pdfs_parser = subparsers.add_parser(
        "parse-pdfs", help="Parse PDFs in pdfs/ folder and attach references to papers"
    )
    parse_pdfs_parser.add_argument("directory", help="Project directory")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Dispatch to appropriate handler
    if args.command == "init":
        init_project(args)
    elif args.command == "add-seed":
        add_seed(args)
    elif args.command == "snowball":
        run_snowball(args)
    elif args.command == "review":
        review(args)
    elif args.command == "export":
        export_results(args)
    elif args.command == "list":
        list_papers(args)
    elif args.command == "show":
        show_paper(args)
    elif args.command == "set-status":
        set_status(args)
    elif args.command == "stats":
        show_stats(args)
    elif args.command == "update-citations":
        update_citations(args)
    elif args.command == "parse-pdfs":
        parse_pdfs(args)


if __name__ == "__main__":
    main()
