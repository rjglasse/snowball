"""Main TUI application using Textual."""

import webbrowser
from pathlib import Path
from typing import Optional
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer
from textual.widgets import (
    Header,
    Footer,
    DataTable,
    Static,
    Button,
    Label,
    TextArea,
    Select,
)
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.worker import Worker, WorkerState

from ..models import Paper, PaperStatus, ReviewProject
from ..storage.json_storage import JSONStorage
from ..snowballing import SnowballEngine
from ..exporters.bibtex import BibTeXExporter
from ..exporters.csv_exporter import CSVExporter
from ..parsers.pdf_parser import PDFParser
from ..paper_utils import (
    get_status_value,
    get_source_value,
    get_sort_key,
    format_paper_rich,
    truncate_title,
)


class ReviewDialog(ModalScreen[Optional[tuple]]):
    """Modal dialog for reviewing a paper."""

    def __init__(self, paper: Paper):
        super().__init__()
        self.paper = paper

    def compose(self) -> ComposeResult:
        with Container(id="review-dialog"):
            yield Label(f"Review: {truncate_title(self.paper.title)}")
            yield Label("\nStatus:")
            yield Select(
                [
                    ("Include", "included"),
                    ("Exclude", "excluded"),
                    ("Maybe", "maybe"),
                    ("Keep Pending", "pending"),
                ],
                value=get_status_value(self.paper.status),
                id="status-select",
            )
            yield Label("\nNotes:")
            yield TextArea(self.paper.notes or "", id="notes-input")
            with Horizontal():
                yield Button("Save", variant="primary", id="save-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-btn":
            status_widget = self.query_one("#status-select", Select)
            notes_widget = self.query_one("#notes-input", TextArea)

            status = status_widget.value
            notes = notes_widget.text

            self.dismiss((status, notes))
        else:
            self.dismiss(None)


class SnowballApp(App):
    """Main Snowball SLR application."""

    TITLE = "Snowball SLR"
    SUB_TITLE = "Systematic Literature Review Tool"

    CSS = """
    /* Color scheme */
    Screen {
        layout: vertical;
        background: #0a0e14;
    }

    /* Stats panel styling */
    #stats-panel {
        height: auto;
        padding: 1;
        border: solid #30363d;
        background: #161b22;
        color: #c9d1d9;
    }

    /* Papers table styling */
    #papers-table {
        height: 1fr;
        width: 100%;
        background: #0d1117;
        border: solid #30363d;
    }

    DataTable > .datatable--header {
        background: #161b22;
        color: #58a6ff;
        text-style: bold;
    }

    DataTable > .datatable--cursor {
        background: #1f6feb 30%;
        color: #ffffff;
    }

    DataTable:focus > .datatable--cursor {
        background: #1f6feb 50%;
    }

    /* Bottom section with details and log */
    #bottom-section {
        height: 15;
        width: 100%;
        layout: horizontal;
    }

    #bottom-section.hidden {
        display: none;
    }

    /* Detail panel (left, 50%) */
    #detail-panel {
        width: 1fr;
        height: 100%;
        background: #0d1117;
        border: solid #30363d;
        overflow-y: auto;
    }

    #detail-content {
        width: 100%;
        padding: 1 2;
        background: #0d1117;
        color: #c9d1d9;
    }

    /* Event log panel (right, 50%) */
    #log-panel {
        width: 1fr;
        height: 100%;
        background: #0d1117;
        border: solid #30363d;
        overflow-y: auto;
        overflow-x: hidden;
    }

    #log-content {
        padding: 0 1;
        color: #8b949e;
        overflow-x: hidden;
    }

    .log-header {
        background: #161b22;
        color: #58a6ff;
        padding: 0 1;
        text-style: bold;
    }

    /* Review dialog styling */
    #review-dialog {
        width: 70;
        height: 30;
        border: thick #58a6ff;
        background: #161b22;
        padding: 2;
    }

    #review-dialog Label {
        color: #c9d1d9;
        margin: 1 0;
    }

    #review-dialog Select {
        background: #0d1117;
        border: solid #30363d;
        margin: 1 0;
    }

    #review-dialog TextArea {
        background: #0d1117;
        border: solid #30363d;
        height: 8;
        margin: 1 0;
    }

    /* Button styling */
    Button {
        margin: 1;
        background: #21262d;
        color: #c9d1d9;
        border: solid #30363d;
    }

    Button:hover {
        background: #30363d;
        border: solid #58a6ff;
    }

    Button.primary {
        background: #1f6feb;
        color: #ffffff;
        border: none;
    }

    Button.primary:hover {
        background: #388bfd;
    }

    /* Header and Footer */
    Header {
        background: #161b22;
        color: #58a6ff;
        border-bottom: tall #30363d;
    }

    Footer {
        background: #161b22;
        color: #8b949e;
        border-top: tall #30363d;
    }

    Footer > .footer--key {
        background: #21262d;
        color: #58a6ff;
    }

    Footer > .footer--description {
        color: #c9d1d9;
    }

    /* Scrollbar styling */
    ScrollableContainer:focus {
        border: tall #58a6ff 50%;
    }
    """

    BINDINGS = [
        # Navigation (show=False as these are standard)
        Binding("up", "cursor_up", "Move up", show=False),
        Binding("down", "cursor_down", "Move down", show=False),
        Binding("enter", "select_cursor", "Toggle details", show=False),
        Binding("space", "select_cursor", "Toggle details", show=False),
        # Review actions (shown in footer)
        Binding("i", "include", "Include"),
        Binding("right", "include", "Include (arrow)", show=False, priority=True),
        Binding("left", "exclude", "Exclude (arrow)", show=False, priority=True),
        Binding("m", "maybe", "Maybe"),
        Binding("n", "notes", "Notes"),
        Binding("u", "undo", "Undo"),
        # Paper actions
        Binding("o", "open", "Open DOI/arXiv"),
        Binding("p", "open_pdf", "Open local PDF"),
        Binding("d", "toggle_details", "Toggle details"),
        Binding("e", "enrich", "Enrich metadata"),
        # Project actions
        Binding("s", "snowball", "Run snowball"),
        Binding("x", "export", "Export"),
        Binding("f", "filter", "Filter papers"),
        Binding("P", "parse_pdfs", "Parse PDFs in pdfs/"),
        # App actions
        Binding("question_mark", "help", "Show help"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        project_dir: Path,
        storage: JSONStorage,
        engine: SnowballEngine,
        project: ReviewProject,
    ):
        super().__init__()
        self.project_dir = project_dir
        self.storage = storage
        self.engine = engine
        self.project = project
        self.current_paper: Optional[Paper] = None

        # Sort state tracking (default: Status ascending for review workflow)
        self.sort_column: str = "Status"
        self.sort_ascending: bool = True  # True = ascending (pending first)
        self.sort_cycle_position: int = 0  # 0=asc, 1=desc, 2=default

        # Filter state: None = all, or PaperStatus value
        self.filter_status: Optional[PaperStatus] = None

        # Worker context for background tasks
        self._worker_context: dict = {}

        # Event log for tracking actions (display format and raw for file)
        self._event_log: list[str] = []
        self._event_log_raw: list[str] = []

        # Undo stack for status changes: (paper_id, previous_status, title)
        self._last_status_change: Optional[tuple[str, PaperStatus, str]] = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(self._get_stats_text(), id="stats-panel")
        yield DataTable(id="papers-table", cursor_type="row")

        # Bottom section with details (left) and log (right)
        with Horizontal(id="bottom-section"):
            # Detail panel (50% width)
            with ScrollableContainer(id="detail-panel"):
                yield Static("Select a paper to view details", id="detail-content", classes="detail-content")

            # Event log panel (50% width)
            with ScrollableContainer(id="log-panel"):
                yield Static("[bold #58a6ff]Event Log[/bold #58a6ff]", classes="log-header")
                yield Static("", id="log-content")

        yield Footer()

    def _get_column_label(self, column_name: str) -> str:
        """Get column label with sort indicator if applicable."""
        if self.sort_column != column_name or self.sort_cycle_position == 2:
            # Not sorted by this column, or in default state
            return column_name

        # Add sort indicator
        if self.sort_ascending:
            return f"{column_name} ▲"
        else:
            return f"{column_name} ▼"

    def _get_sort_key(self, paper: Paper):
        """Generate sort key for a paper based on current sort column.

        Returns a tuple where the first element controls None/missing value ordering,
        and the second element is the actual value for comparison.
        """
        return get_sort_key(paper, self.sort_column)

    def on_mount(self) -> None:
        """Set up the table when app starts."""
        table = self.query_one("#papers-table", DataTable)

        # Add columns with sort indicators
        table.add_columns(
            self._get_column_label("Status"),
            self._get_column_label("Title"),
            self._get_column_label("Year"),
            self._get_column_label("Cite"),
            self._get_column_label("Source"),
            self._get_column_label("Iter"),
            self._get_column_label("Obs"),
            "PDF",
        )

        # Load and display papers
        self._refresh_table()

        # Load existing event log from file
        self._load_event_log()

        # Update log panel with loaded entries
        if self._event_log:
            log_content = self.query_one("#log-content", Static)
            log_content.update("\n".join(self._event_log))

        # Log startup
        stats = self.storage.get_statistics()
        self._log_event(f"[#58a6ff]Loaded:[/#58a6ff] {stats['total']} papers")

        # Show first paper's details if available
        papers = self.storage.load_all_papers()
        if papers:
            self._show_paper_details(papers[0])

    def _refresh_table(self) -> None:
        """Refresh the papers table."""
        table = self.query_one("#papers-table", DataTable)

        # Clear table including columns to update headers with sort indicators
        table.clear(columns=True)

        # Re-add columns with updated sort indicators
        table.add_columns(
            self._get_column_label("Status"),
            self._get_column_label("Title"),
            self._get_column_label("Year"),
            self._get_column_label("Cite"),
            self._get_column_label("Source"),
            self._get_column_label("Iter"),
            self._get_column_label("Obs"),
            "PDF",
        )

        papers = self.storage.load_all_papers()

        # Apply status filter if set
        if self.filter_status is not None:
            papers = [p for p in papers if p.status == self.filter_status]

        # Sort papers using current sort settings
        papers.sort(key=self._get_sort_key, reverse=not self.sort_ascending)

        for paper in papers:
            # Status indicator with icon and text
            status_val = get_status_value(paper.status)
            status_display = {
                "included": "[#3fb950]✓ Included[/#3fb950]",
                "excluded": "[#f85149]✗ Excluded[/#f85149]",
                "pending": "[#d29922]? Pending[/#d29922]",
                "maybe": "[#a371f7]~ Maybe[/#a371f7]",
            }.get(status_val, "?")

            # Title (truncate for readability)
            title = truncate_title(paper.title, max_length=160)

            # Citations
            citations = str(paper.citation_count) if paper.citation_count is not None else "-"

            # Source
            source = get_source_value(paper.source)
            source_short = {"seed": "Seed", "backward": "Bkd", "forward": "Fwd"}.get(source, source)

            # PDF indicator
            pdf_indicator = "[#58a6ff]pdf[/#58a6ff]" if paper.pdf_path else ""

            # Observation count
            obs_count = str(paper.observation_count) if paper.observation_count > 1 else ""

            table.add_row(
                status_display,
                title,
                str(paper.year) if paper.year else "-",
                citations,
                source_short,
                str(paper.snowball_iteration),
                obs_count,
                pdf_indicator,
                key=paper.id,
            )

        # Update stats
        stats_panel = self.query_one("#stats-panel", Static)
        stats_panel.update(self._get_stats_text())

    def _get_stats_text(self) -> str:
        """Get statistics text."""
        stats = self.storage.get_statistics()
        total = stats["total"]
        by_status = stats.get("by_status", {})

        included = by_status.get("included", 0)
        excluded = by_status.get("excluded", 0)
        pending = by_status.get("pending", 0)
        maybe = by_status.get("maybe", 0)

        # Filter indicator
        if self.filter_status is None:
            filter_text = "[bold]Filter:[/bold] All"
        elif self.filter_status == PaperStatus.PENDING:
            filter_text = "[bold]Filter:[/bold] [#d29922]Pending[/#d29922]"
        elif self.filter_status == PaperStatus.INCLUDED:
            filter_text = "[bold]Filter:[/bold] [#3fb950]Included[/#3fb950]"
        elif self.filter_status == PaperStatus.EXCLUDED:
            filter_text = "[bold]Filter:[/bold] [#f85149]Excluded[/#f85149]"
        elif self.filter_status == PaperStatus.MAYBE:
            filter_text = "[bold]Filter:[/bold] [#a371f7]Maybe[/#a371f7]"
        else:
            filter_text = "[bold]Filter:[/bold] All"

        return (
            f"[bold #58a6ff]{self.project.name}[/bold #58a6ff] [dim]│[/dim] "
            f"[bold]Total:[/bold] [#58a6ff]{total}[/#58a6ff] [dim]│[/dim] "
            f"[#3fb950]✓ {included}[/#3fb950] [dim]│[/dim] "
            f"[#f85149]✗ {excluded}[/#f85149] [dim]│[/dim] "
            f"[#d29922]? {pending}[/#d29922] [dim]│[/dim] "
            f"[#a371f7]~ {maybe}[/#a371f7] [dim]│[/dim] "
            f"{filter_text} [dim]│[/dim] "
            f"[bold]Iter:[/bold] [#a371f7]{self.project.current_iteration}[/#a371f7]"
        )

    def _format_paper_details(self, paper: Paper) -> str:
        """Format paper details as rich text using shared function."""
        return format_paper_rich(paper)

    def _show_paper_details(self, paper: Paper) -> None:
        """Show details for a paper in the detail panel."""
        self.current_paper = paper
        details_text = self._format_paper_details(paper)

        # Update the content
        detail_content = self.query_one("#detail-content", Static)
        detail_content.update(details_text)

    def _log_event(self, message: str) -> None:
        """Add an event to the log panel and persist to file."""
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Store with full timestamp for file, display with short timestamp
        display_entry = f"[dim]{timestamp[11:]}[/dim] {message}"
        file_entry = f"{timestamp} {message}"

        # Insert at beginning (newest first)
        self._event_log.insert(0, display_entry)
        self._event_log_raw.insert(0, file_entry)

        # Keep only last 100 entries
        if len(self._event_log) > 100:
            self._event_log = self._event_log[:100]
            self._event_log_raw = self._event_log_raw[:100]

        # Persist to file
        self._save_event_log()

        # Update the log panel
        log_content = self.query_one("#log-content", Static)
        log_content.update("\n".join(self._event_log))

    def _load_event_log(self) -> None:
        """Load event log from file (stored newest first)."""
        log_file = self.project_dir / "event_log.txt"
        self._event_log = []
        self._event_log_raw = []

        if log_file.exists():
            try:
                with open(log_file, "r") as f:
                    lines = f.read().strip().split("\n")
                    # Keep first 100 entries (newest first in file)
                    lines = lines[:100] if len(lines) > 100 else lines
                    for line in lines:
                        if line.strip():
                            self._event_log_raw.append(line)
                            # Convert to display format (extract time portion)
                            if len(line) >= 19:  # "YYYY-MM-DD HH:MM:SS"
                                time_part = line[11:19]
                                msg_part = line[20:] if len(line) > 20 else ""
                                self._event_log.append(f"[dim]{time_part}[/dim] {msg_part}")
                            else:
                                self._event_log.append(line)
            except Exception:
                pass  # Start fresh if file is corrupted

    def _save_event_log(self) -> None:
        """Save event log to file."""
        log_file = self.project_dir / "event_log.txt"
        try:
            with open(log_file, "w") as f:
                f.write("\n".join(self._event_log_raw))
        except Exception:
            pass  # Ignore save errors

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Handle row cursor movement - show details automatically."""
        if event.row_key is None:
            return

        paper_id = event.row_key.value
        paper = self.storage.load_paper(paper_id)

        if paper:
            self._show_paper_details(paper)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection (Enter key) - show paper details."""
        paper_id = event.row_key.value
        paper = self.storage.load_paper(paper_id)

        if paper:
            self._show_paper_details(paper)

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        """Handle column header clicks for sorting."""
        # Get clicked column label (strip any existing sort indicators)
        # event.label is a Rich Text object, convert to string first
        clicked_column = str(event.label).replace(" ▲", "").replace(" ▼", "")

        # Determine next state in the cycle
        if self.sort_column == clicked_column:
            # Same column clicked - advance through cycle
            self.sort_cycle_position = (self.sort_cycle_position + 1) % 3

            if self.sort_cycle_position == 0:
                # First click: ascending
                self.sort_ascending = True
            elif self.sort_cycle_position == 1:
                # Second click: descending
                self.sort_ascending = False
            else:
                # Third click: reset to default (Status ascending)
                self.sort_column = "Status"
                self.sort_ascending = True
                self.sort_cycle_position = 0
        else:
            # Different column clicked - start fresh at ascending
            self.sort_column = clicked_column
            self.sort_ascending = True
            self.sort_cycle_position = 0

        # Refresh table with new sort
        self._refresh_table()

    def _update_paper_status(self, status: PaperStatus) -> None:
        """Update the status of the currently selected paper and stay on next."""
        if not self.current_paper:
            return

        # Save for undo before changing
        self._last_status_change = (
            self.current_paper.id,
            self.current_paper.status,
            self.current_paper.title,
        )

        # Get the current table position
        table = self.query_one("#papers-table", DataTable)
        current_row_index = table.cursor_row

        # Log the status change
        status_labels = {
            PaperStatus.INCLUDED: "[#3fb950]Included:[/#3fb950]",
            PaperStatus.EXCLUDED: "[#f85149]Excluded:[/#f85149]",
            PaperStatus.MAYBE: "[#a371f7]Maybe:[/#a371f7]",
            PaperStatus.PENDING: "[#d29922]Pending:[/#d29922]",
        }
        self._log_event(f"{status_labels.get(status, status.value + ':')} {self.current_paper.title}")

        # Update the paper status (pass project for iteration stats tracking)
        self.engine.update_paper_review(
            self.current_paper.id,
            status,
            self.current_paper.notes,  # Keep existing notes
            project=self.project
        )

        # Refresh the table to show updated status
        self._refresh_table()

        # Stay at same row position - the judged paper moves away due to sort,
        # so the "next" paper naturally slides into current position
        table = self.query_one("#papers-table", DataTable)
        if table.row_count > 0:
            # Stay at current position, or last row if we're beyond the end
            target_row = min(current_row_index, table.row_count - 1)
            table.move_cursor(row=target_row)

            # The move_cursor will trigger on_data_table_row_highlighted
            # which will show the details automatically

    def action_include(self) -> None:
        """Mark the selected paper as included."""
        self._update_paper_status(PaperStatus.INCLUDED)

    def action_exclude(self) -> None:
        """Mark the selected paper as excluded."""
        self._update_paper_status(PaperStatus.EXCLUDED)

    def action_maybe(self) -> None:
        """Mark the selected paper as maybe."""
        self._update_paper_status(PaperStatus.MAYBE)

    def action_pending(self) -> None:
        """Mark the selected paper as pending."""
        self._update_paper_status(PaperStatus.PENDING)

    def action_undo(self) -> None:
        """Undo the last status change."""
        if not self._last_status_change:
            self.notify("Nothing to undo", severity="warning")
            return

        paper_id, previous_status, title = self._last_status_change

        # Load the paper and restore its status
        paper = self.storage.load_paper(paper_id)
        if not paper:
            self.notify("Paper not found", severity="error")
            return

        # Update the paper status back to previous
        self.engine.update_paper_review(
            paper_id,
            previous_status,
            paper.notes,
            project=self.project
        )

        # Log the undo
        status_labels = {
            PaperStatus.INCLUDED: "[#3fb950]Included[/#3fb950]",
            PaperStatus.EXCLUDED: "[#f85149]Excluded[/#f85149]",
            PaperStatus.MAYBE: "[#a371f7]Maybe[/#a371f7]",
            PaperStatus.PENDING: "[#d29922]Pending[/#d29922]",
        }
        status_label = status_labels.get(previous_status, previous_status.value)
        self._log_event(f"[dim]Undo:[/dim] {title} → {status_label}")

        # Clear the undo state (can only undo once)
        self._last_status_change = None

        # Refresh display
        self._refresh_table()
        self.notify(f"Undone: restored to {previous_status.value}", severity="information")

    def action_notes(self) -> None:
        """Add/edit notes for the selected paper."""
        if not self.current_paper:
            return

        # Use the ReviewDialog just for notes editing
        def handle_notes(result: Optional[tuple]) -> None:
            if result:
                _, notes = result
                self.engine.update_paper_review(
                    self.current_paper.id, self.current_paper.status, notes  # Keep existing status
                )
                self._refresh_table()

                # Reload current paper and update detail panel
                self.current_paper = self.storage.load_paper(self.current_paper.id)
                if self.current_paper:
                    self._show_paper_details(self.current_paper)

        self.push_screen(ReviewDialog(self.current_paper), handle_notes)

    def action_open(self) -> None:
        """Open the paper's DOI or arXiv URL in browser."""
        if not self.current_paper:
            return

        # Prefer DOI, fallback to arXiv
        url = None
        if self.current_paper.doi:
            url = f"https://doi.org/{self.current_paper.doi}"
        elif self.current_paper.arxiv_id:
            url = f"https://arxiv.org/abs/{self.current_paper.arxiv_id}"

        if url:
            webbrowser.open(url)

    def action_open_pdf(self) -> None:
        """Open the local PDF file if available."""
        if not self.current_paper:
            return

        if self.current_paper.pdf_path:
            pdf_path = Path(self.current_paper.pdf_path)
            if pdf_path.exists():
                webbrowser.open(f"file://{pdf_path.absolute()}")
            else:
                self.notify(f"PDF file not found: {pdf_path}", severity="error")
        else:
            self.notify("No local PDF for this paper", severity="warning")

    def action_snowball(self) -> None:
        """Run a snowball iteration."""
        # Store context
        old_count = len(self.storage.load_all_papers())
        self._worker_context["snowball"] = {"old_count": old_count}

        # Show working notification
        self.notify("Running snowball...", timeout=60)

        def do_snowball() -> int:
            """Run snowball in background thread."""
            self.engine.run_snowball_iteration(self.project)
            return len(self.storage.load_all_papers())

        self.run_worker(do_snowball, name="snowball", thread=True)

    def _handle_snowball_complete(self) -> None:
        """Handle snowball worker completion."""
        ctx = self._worker_context.get("snowball", {})
        old_count = ctx.get("old_count", 0)

        self.project = self.storage.load_project()
        new_count = len(self.storage.load_all_papers())
        new_papers = new_count - old_count

        self._refresh_table()

        if new_papers > 0:
            self.notify(f"Found {new_papers} new papers", title="Snowball complete", severity="information")
            self._log_event(f"[#a371f7]Snowball:[/#a371f7] iteration {self.project.current_iteration}, +{new_papers} papers")
        else:
            self.notify("No new papers found", title="Snowball complete", severity="warning")
            self._log_event(f"[#a371f7]Snowball:[/#a371f7] iteration {self.project.current_iteration}, no new papers")

    def action_export(self) -> None:
        """Export papers."""
        papers = self.storage.load_all_papers()
        included_count = sum(1 for p in papers if p.status == PaperStatus.INCLUDED)

        # Export BibTeX
        bibtex_exporter = BibTeXExporter()
        bibtex_content = bibtex_exporter.export(papers, only_included=True)
        bibtex_path = self.project_dir / "export_included.bib"
        with open(bibtex_path, "w") as f:
            f.write(bibtex_content)

        # Export CSV
        csv_exporter = CSVExporter()
        csv_path = self.project_dir / "export_all.csv"
        csv_exporter.export(papers, csv_path, only_included=False)

        self.notify("Exported BibTeX and CSV", title="Export complete", severity="information")
        self._log_event(f"[#d29922]Exported:[/#d29922] {included_count} included → BibTeX, {len(papers)} total → CSV")

    def action_filter(self) -> None:
        """Cycle through filter states: all → pending → included → excluded → maybe → all."""
        # Define the cycle order
        cycle = [None, PaperStatus.PENDING, PaperStatus.INCLUDED, PaperStatus.EXCLUDED, PaperStatus.MAYBE]

        # Find current position and move to next
        try:
            current_index = cycle.index(self.filter_status)
            next_index = (current_index + 1) % len(cycle)
        except ValueError:
            next_index = 0

        self.filter_status = cycle[next_index]

        # Refresh table with new filter
        self._refresh_table()

        # Move cursor to first row if there are papers
        table = self.query_one("#papers-table", DataTable)
        if table.row_count > 0:
            table.move_cursor(row=0)

    def action_parse_pdfs(self) -> None:
        """Scan pdfs/ folder and parse any PDFs, matching to papers by title."""
        pdfs_dir = self.project_dir / "pdfs"

        if not pdfs_dir.exists():
            self.notify("No pdfs/ folder found", severity="warning")
            return

        pdf_files = list(pdfs_dir.glob("*.pdf"))
        if not pdf_files:
            self.notify("No PDF files in pdfs/ folder", severity="warning")
            return

        # Store context
        self._worker_context["parse_pdfs"] = {"pdf_files": pdf_files}

        # Show working notification
        self.notify(f"Parsing {len(pdf_files)} PDFs...", timeout=60)

        def do_parse() -> dict:
            """Parse PDFs in background thread."""
            all_papers = self.storage.load_all_papers()
            pdf_parser = PDFParser()

            processed = 0
            no_match = 0

            for pdf_path in pdf_files:
                # Skip if already linked to a paper
                already_linked = any(
                    p.pdf_path and Path(p.pdf_path).name == pdf_path.name
                    for p in all_papers
                )
                if already_linked:
                    continue

                try:
                    result = pdf_parser.parse(pdf_path)
                    if not result.title:
                        continue

                    # Find matching paper by title (fuzzy match)
                    matched_paper = self._find_paper_by_title_fuzzy(all_papers, result.title)

                    if matched_paper:
                        # Store references
                        if result.references:
                            if matched_paper.raw_data is None:
                                matched_paper.raw_data = {}
                            matched_paper.raw_data["grobid_references"] = result.references

                        matched_paper.pdf_path = str(pdf_path)
                        self.storage.save_paper(matched_paper)
                        processed += 1
                    else:
                        no_match += 1

                except Exception:
                    pass  # Skip failed parses silently

            # Store results in context for handler
            self._worker_context["parse_pdfs"]["processed"] = processed
            self._worker_context["parse_pdfs"]["no_match"] = no_match
            return {"processed": processed, "no_match": no_match}

        self.run_worker(do_parse, name="parse_pdfs", thread=True)

    def _handle_parse_pdfs_complete(self) -> None:
        """Handle parse PDFs worker completion."""
        ctx = self._worker_context.get("parse_pdfs", {})
        processed = ctx.get("processed", 0)
        no_match = ctx.get("no_match", 0)

        self._refresh_table()

        if processed > 0 or no_match > 0:
            self.notify(
                f"Matched: {processed}, No match: {no_match}",
                title="Parse complete",
                severity="information" if processed > 0 else "warning"
            )
            self._log_event(f"[#58a6ff]PDF parse:[/#58a6ff] matched {processed}, unmatched {no_match}")
        else:
            self.notify("No new PDFs to process", severity="information")

    def _find_paper_by_title_fuzzy(self, papers: list, title: str, threshold: float = 0.8):
        """Find a paper by fuzzy title match."""
        if not title:
            return None

        best_match = None
        best_score = 0

        stopwords = {'a', 'an', 'the', 'of', 'in', 'on', 'for', 'to', 'and', 'or', 'with'}

        words1 = set(title.lower().split()) - stopwords
        if not words1:
            return None

        for paper in papers:
            if not paper.title:
                continue

            words2 = set(paper.title.lower().split()) - stopwords
            if not words2:
                continue

            intersection = len(words1 & words2)
            union = len(words1 | words2)
            similarity = intersection / union if union > 0 else 0

            if similarity >= threshold and similarity > best_score:
                best_score = similarity
                best_match = paper

        return best_match

    def action_toggle_details(self) -> None:
        """Toggle the bottom section (details + log) visibility."""
        bottom_section = self.query_one("#bottom-section")
        if bottom_section.has_class("hidden"):
            bottom_section.remove_class("hidden")
        else:
            bottom_section.add_class("hidden")

    def action_enrich(self) -> None:
        """Enrich the current paper's metadata from APIs."""
        if not self.current_paper:
            self.notify("No paper selected", severity="warning")
            return

        paper = self.current_paper

        # Save current cursor position
        table = self.query_one("#papers-table", DataTable)
        current_row_index = table.cursor_row

        # Store context for worker completion handler
        self._worker_context["enrich"] = {
            "paper": paper,
            "had_abstract": bool(paper.abstract),
            "had_year": paper.year is not None,
            "had_citations": paper.citation_count is not None,
            "had_doi": bool(paper.doi),
            "cursor_row": current_row_index,
        }

        # Show working notification
        self.notify("Enriching metadata...", timeout=30)

        def do_enrich() -> str:
            """Run enrichment in background thread."""
            self.engine.api.enrich_metadata(paper)
            self.storage.save_paper(paper)
            return "enrich"

        self.run_worker(do_enrich, name="enrich", thread=True)

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle worker completion."""
        if event.state != WorkerState.SUCCESS and event.state != WorkerState.ERROR:
            return

        worker_name = event.worker.name

        # Clear the "working" notification before showing result
        self.clear_notifications()

        if event.state == WorkerState.ERROR:
            self.notify(f"Operation failed: {event.worker.error}", title="Error", severity="error")
            return

        if worker_name == "enrich":
            self._handle_enrich_complete()
        elif worker_name == "snowball":
            self._handle_snowball_complete()
        elif worker_name == "parse_pdfs":
            self._handle_parse_pdfs_complete()

    def _handle_enrich_complete(self) -> None:
        """Handle enrich worker completion."""
        ctx = self._worker_context.get("enrich", {})
        paper = ctx.get("paper")

        if not paper:
            return

        # Build report of what was added
        updates = []
        if not ctx.get("had_abstract") and paper.abstract:
            updates.append("abstract")
        if not ctx.get("had_year") and paper.year:
            updates.append("year")
        if not ctx.get("had_citations") and paper.citation_count is not None:
            updates.append("citations")
        if not ctx.get("had_doi") and paper.doi:
            updates.append("DOI")

        if updates:
            self.notify(f"Added: {', '.join(updates)}", title="Enriched", severity="information")
            self._log_event(f"[#58a6ff]Enriched:[/#58a6ff] {paper.title} +{', '.join(updates)}")
        else:
            self.notify("No new metadata found", title="Enriched", severity="warning")
            self._log_event(f"[#58a6ff]Enriched:[/#58a6ff] {paper.title} (no new data)")

        # Refresh display
        self._show_paper_details(paper)
        self._refresh_table()

        # Restore cursor position
        table = self.query_one("#papers-table", DataTable)
        if table.row_count > 0:
            target_row = min(ctx.get("cursor_row", 0), table.row_count - 1)
            table.move_cursor(row=target_row)

    def action_help(self) -> None:
        """Show help with all keybindings."""
        help_text = """
[bold cyan]Snowball Review - Keyboard Shortcuts[/bold cyan]

[bold]Navigation:[/bold]
  ↑/↓         Move between papers
  Enter/Space Toggle paper details
  d           Toggle details panel

[bold]Review Actions:[/bold]
  i / →       Include paper (moves to next)
  ←           Exclude paper (moves to next)
  m           Mark as Maybe
  n           Add/edit notes

[bold]Paper Actions:[/bold]
  o           Open DOI/arXiv in browser
  p           Open local PDF
  e           Enrich metadata from APIs

[bold]Table:[/bold]
  Click header Sort by column (cycles: asc → desc → default)

[bold]Project Actions:[/bold]
  s           Run snowball iteration
  x           Export papers (BibTeX + CSV)
  f           Filter papers (cycles: all → pending → included → excluded → maybe)
  P           Parse PDFs in pdfs/ folder (Shift+P)

[bold]Other:[/bold]
  Ctrl+P      Command palette
  ?           Show this help
  q           Quit

Press any key to close this help.
"""
        from textual.widgets import Static
        from textual.containers import Container

        # Simple notification-style help
        self.notify(help_text, title="Help", timeout=30)


def run_tui(
    project_dir: Path, storage: JSONStorage, engine: SnowballEngine, project: ReviewProject
) -> None:
    """Run the TUI application."""
    app = SnowballApp(project_dir, storage, engine, project)
    app.run()
