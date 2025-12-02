"""Command-line interface for Snowball SLR tool."""

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


# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def init_project(args) -> None:
    """Initialize a new SLR project."""
    project_dir = Path(args.directory)

    if project_dir.exists() and any(project_dir.iterdir()):
        logger.error(f"Directory {project_dir} already exists and is not empty")
        sys.exit(1)

    project_dir.mkdir(parents=True, exist_ok=True)

    # Create storage
    storage = JSONStorage(project_dir)

    # Create project
    project = ReviewProject(
        name=args.name or project_dir.name,
        description=args.description or "",
        max_iterations=args.max_iterations or 1,
    )

    # Set up filters if provided
    if args.min_year or args.max_year:
        project.filter_criteria = FilterCriteria(min_year=args.min_year, max_year=args.max_year)

    # Save project
    storage.save_project(project)

    logger.info(f"Initialized project '{project.name}' in {project_dir}")
    logger.info(f"Max iterations: {project.max_iterations}")


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
    api = APIAggregator(s2_api_key=args.s2_api_key, email=args.email)
    pdf_parser = PDFParser(use_grobid=not args.no_grobid)
    engine = SnowballEngine(storage, api, pdf_parser)

    # Add seeds
    added_count = 0

    if args.pdf:
        for pdf_path in args.pdf:
            pdf_file = Path(pdf_path)
            if not pdf_file.exists():
                logger.warning(f"PDF not found: {pdf_file}")
                continue

            paper = engine.add_seed_from_pdf(pdf_file, project)
            if paper:
                logger.info(f"Added seed: {paper.title}")
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
    api = APIAggregator(s2_api_key=args.s2_api_key, email=args.email)
    engine = SnowballEngine(storage, api)

    # Run iterations
    iteration_count = 0
    while engine.should_continue_snowballing(project):
        logger.info(f"\nRunning snowball iteration {project.current_iteration + 1}...")

        stats = engine.run_snowball_iteration(project)

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
    api = APIAggregator(s2_api_key=args.s2_api_key, email=args.email)
    engine = SnowballEngine(storage, api)

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

    # Filter by status if specified
    if args.status:
        papers = [p for p in papers if _get_status_value(p.status) == args.status]

    # Filter by iteration if specified
    if args.iteration is not None:
        papers = [p for p in papers if p.snowball_iteration == args.iteration]

    # Filter by source if specified
    if args.source:
        papers = [p for p in papers if _get_source_value(p.source) == args.source]

    # Sort papers
    if args.sort == "citations":
        papers.sort(key=lambda p: (p.citation_count is None, -(p.citation_count or 0)))
    elif args.sort == "year":
        papers.sort(key=lambda p: (p.year is None, -(p.year or 0)))
    elif args.sort == "title":
        papers.sort(key=lambda p: p.title.lower())
    elif args.sort == "status":
        status_order = {"pending": 0, "included": 1, "excluded": 2, "maybe": 3}
        papers.sort(key=lambda p: status_order.get(_get_status_value(p.status), 999))

    # Output format
    if args.format == "json":
        output = []
        for paper in papers:
            output.append(
                {
                    "id": paper.id,
                    "title": paper.title,
                    "year": paper.year,
                    "status": _get_status_value(paper.status),
                    "source": _get_source_value(paper.source),
                    "iteration": paper.snowball_iteration,
                    "citations": paper.citation_count,
                    "doi": paper.doi,
                    "arxiv_id": paper.arxiv_id,
                }
            )
        print(json.dumps(output, indent=2))
    else:
        # Table format
        print(f"\n{'ID':<38} {'Status':<10} {'Year':<6} {'Citations':<10} {'Title'}")
        print("-" * 120)
        for paper in papers:
            status = _get_status_value(paper.status)
            year = str(paper.year) if paper.year else "-"
            citations = str(paper.citation_count) if paper.citation_count is not None else "-"
            title = paper.title[:60] + "..." if len(paper.title) > 60 else paper.title
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
        output = {
            "id": paper.id,
            "title": paper.title,
            "authors": [a.name for a in paper.authors] if paper.authors else [],
            "year": paper.year,
            "abstract": paper.abstract,
            "doi": paper.doi,
            "arxiv_id": paper.arxiv_id,
            "status": _get_status_value(paper.status),
            "source": _get_source_value(paper.source),
            "iteration": paper.snowball_iteration,
            "citations": paper.citation_count,
            "influential_citations": paper.influential_citation_count,
            "venue": paper.venue.name if paper.venue else None,
            "notes": paper.notes,
            "tags": paper.tags,
        }
        print(json.dumps(output, indent=2))
    else:
        # Human-readable format
        print(f"\n{'=' * 80}")
        print(f"Title: {paper.title}")
        print(f"{'=' * 80}")
        print(f"ID:       {paper.id}")
        print(f"Status:   {_get_status_value(paper.status)}")
        print(f"Source:   {_get_source_value(paper.source)} (iteration {paper.snowball_iteration})")
        print()

        if paper.authors:
            authors = ", ".join([a.name for a in paper.authors[:10]])
            if len(paper.authors) > 10:
                authors += f" (+{len(paper.authors) - 10} more)"
            print(f"Authors:  {authors}")

        if paper.year:
            print(f"Year:     {paper.year}")

        if paper.venue and paper.venue.name:
            print(f"Venue:    {paper.venue.name}")

        if paper.doi:
            print(f"DOI:      {paper.doi}")

        if paper.arxiv_id:
            print(f"arXiv:    {paper.arxiv_id}")

        if paper.citation_count is not None:
            cit_text = str(paper.citation_count)
            if paper.influential_citation_count:
                cit_text += f" (influential: {paper.influential_citation_count})"
            print(f"Citations: {cit_text}")

        if paper.abstract:
            print(f"\nAbstract:\n{paper.abstract}")

        if paper.notes:
            print(f"\nNotes:\n{paper.notes}")

        if paper.tags:
            print(f"\nTags: {', '.join(paper.tags)}")

        print()


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
        "maybe": PaperStatus.MAYBE,
    }

    new_status = status_map.get(args.status)
    if not new_status:
        logger.error(f"Invalid status: {args.status}")
        sys.exit(1)

    # Update paper
    old_status = _get_status_value(paper.status)
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

    stats = storage.get_statistics()

    if args.format == "json":
        output = {
            "project_name": project.name,
            "current_iteration": project.current_iteration,
            "max_iterations": project.max_iterations,
            "total_papers": stats["total"],
            "by_status": stats["by_status"],
            "by_iteration": stats["by_iteration"],
            "by_source": stats["by_source"],
            "seed_count": len(project.seed_paper_ids),
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"\n{'=' * 50}")
        print(f"Project: {project.name}")
        print(f"{'=' * 50}")
        print(f"Current iteration: {project.current_iteration} / {project.max_iterations}")
        print(f"Seed papers:       {len(project.seed_paper_ids)}")
        print(f"Total papers:      {stats['total']}")
        print()
        print("By Status:")
        for status, count in stats["by_status"].items():
            print(f"  {status}: {count}")
        print()
        print("By Iteration:")
        for iteration, count in sorted(stats["by_iteration"].items(), key=lambda x: int(x[0])):
            print(f"  Iteration {iteration}: {count}")
        print()
        print("By Source:")
        for source, count in stats["by_source"].items():
            print(f"  {source}: {count}")
        print()


def _get_status_value(status) -> str:
    """Get string value from status (handles both enum and string)."""
    return status.value if hasattr(status, "value") else status


def _get_source_value(source) -> str:
    """Get string value from source (handles both enum and string)."""
    return source.value if hasattr(source, "value") else source


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
    init_parser.add_argument(
        "--max-iterations", type=int, default=1, help="Maximum snowball iterations"
    )
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

    # Snowball command
    snowball_parser = subparsers.add_parser("snowball", help="Run snowballing iterations")
    snowball_parser.add_argument("directory", help="Project directory")
    snowball_parser.add_argument("--iterations", type=int, help="Number of iterations to run")
    snowball_parser.add_argument("--s2-api-key", help="Semantic Scholar API key")
    snowball_parser.add_argument("--email", help="Email for API polite pools")

    # Review command
    review_parser = subparsers.add_parser("review", help="Launch interactive review interface")
    review_parser.add_argument("directory", help="Project directory")
    review_parser.add_argument("--s2-api-key", help="Semantic Scholar API key")
    review_parser.add_argument("--email", help="Email for API polite pools")

    # Export command
    export_parser = subparsers.add_parser("export", help="Export results")
    export_parser.add_argument("directory", help="Project directory")
    export_parser.add_argument(
        "--format", choices=["bibtex", "csv", "all"], default="all", help="Export format"
    )
    export_parser.add_argument("--output", help="Output directory")
    export_parser.add_argument(
        "--included-only", action="store_true", help="Only export included papers"
    )

    # List command (non-interactive)
    list_parser = subparsers.add_parser(
        "list", help="List papers non-interactively (for AI agents/scripts)"
    )
    list_parser.add_argument("directory", help="Project directory")
    list_parser.add_argument(
        "--status", choices=["pending", "included", "excluded", "maybe"], help="Filter by status"
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
        choices=["pending", "included", "excluded", "maybe"],
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


if __name__ == "__main__":
    main()
