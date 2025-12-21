"""Main TUI application using Textual."""

import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer
from textual.coordinate import Coordinate
from textual.widgets import (
    Header,
    Footer,
    DataTable,
    Static,
    Button,
    Label,
    TextArea,
    Select,
    Input,
)
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.worker import Worker, WorkerState

from ..models import Paper, PaperStatus, ReviewProject
from ..storage.json_storage import JSONStorage
from ..snowballing import SnowballEngine
from ..exporters.bibtex import BibTeXExporter
from ..exporters.csv_exporter import CSVExporter
from ..exporters.tikz import TikZExporter
from ..parsers.pdf_parser import PDFParser
from ..paper_utils import (
    get_status_value,
    get_source_value,
    get_sort_key,
    format_paper_rich,
    truncate_title,
    titles_match,
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


class MetadataMismatchDialog(ModalScreen[Optional[dict]]):
    """Dialog to show metadata mismatches and let user approve/reject changes."""

    # Use unique prefix to avoid catching events from other buttons
    BUTTON_PREFIX = "mismatch-"

    def __init__(self, mismatches: list[tuple[str, str, str]], doi: str = None):
        """Initialize with list of (field_name, current_value, api_value) tuples."""
        super().__init__()
        self.mismatches = mismatches
        self.doi = doi
        # Note: Can't use "selections" as it conflicts with Textual's Screen.selections
        self.field_choices: dict[str, bool] = {m[0]: False for m in mismatches}

    def compose(self) -> ComposeResult:
        with Container(id="mismatch-dialog"):
            yield Label("[bold #d29922]Metadata Mismatch Detected[/bold #d29922]\n")

            if self.doi:
                yield Label(f"[dim]DOI: {self.doi}[/dim]")
                yield Label("The DOI lookup returned different values than the PDF/current data.")
                yield Label("[dim]Note: PDF extraction (GROBID) can be imperfect. If you have a DOI,[/dim]")
                yield Label("[dim]the API values are likely more accurate.[/dim]\n")
            else:
                yield Label("The API returned different values. Compare and choose:\n")

            for field, current, api_val in self.mismatches:
                yield Label(f"[bold]{field}:[/bold]")
                current_display = current[:100] + ('...' if len(current) > 100 else '')
                api_display = api_val[:100] + ('...' if len(api_val) > 100 else '')
                yield Label(f"  [dim]PDF/Current:[/dim] {current_display}")
                yield Label(f"  [#58a6ff]API/DOI:[/#58a6ff] {api_display}")
                yield Button(f"Use API {field}", id=f"{self.BUTTON_PREFIX}update-{field}", variant="primary")
                yield Label("")  # Spacer

            with Horizontal():
                yield Button("Keep Current", variant="default", id=f"{self.BUTTON_PREFIX}done")
                if self.doi:
                    yield Button("Trust DOI (Update All)", variant="success", id=f"{self.BUTTON_PREFIX}update-all")
                else:
                    yield Button("Use All API Values", variant="warning", id=f"{self.BUTTON_PREFIX}update-all")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if not button_id or not button_id.startswith(self.BUTTON_PREFIX):
            return  # Not our button

        # Stop event propagation
        event.stop()

        # Strip prefix to get the action
        action = button_id[len(self.BUTTON_PREFIX):]

        if action == "done":
            self.dismiss(self.field_choices)
        elif action == "update-all":
            for field, _, _ in self.mismatches:
                self.field_choices[field] = True
            self.dismiss(self.field_choices)
        elif action.startswith("update-"):
            field = action[7:]  # Remove "update-" prefix
            self.field_choices[field] = True
            self.dismiss(self.field_choices)


class PDFChooserDialog(ModalScreen[Optional[str]]):
    """Dialog to choose a PDF file to link to the current paper."""

    BUTTON_PREFIX = "pdf-"

    def __init__(
        self,
        pdf_files: list[Path],
        current_pdf: Optional[str] = None,
        inbox_dir: Optional[Path] = None,
    ):
        """Initialize with list of available PDF files.

        Args:
            pdf_files: List of PDF file paths
            current_pdf: Currently linked PDF path (if any)
            inbox_dir: Path to inbox directory (to identify unmatched PDFs)
        """
        super().__init__()
        self.pdf_files = pdf_files
        self.current_pdf = current_pdf
        self.inbox_dir = inbox_dir

    def compose(self) -> ComposeResult:
        with Container(id="pdf-dialog"):
            yield Label("[bold #58a6ff]Link PDF to Paper[/bold #58a6ff]\n")

            if self.current_pdf:
                yield Label(f"[dim]Currently linked:[/dim] {Path(self.current_pdf).name}")
                yield Button("Clear link", id=f"{self.BUTTON_PREFIX}clear", variant="error")
                yield Label("")

            if not self.pdf_files:
                yield Label("[dim]No PDFs in pdfs/ or pdfs/inbox/[/dim]")
            else:
                yield Label(f"[dim]Available PDFs ({len(self.pdf_files)}):[/dim]\n")

                # Show scrollable list of PDFs
                with ScrollableContainer(id="pdf-list"):
                    for idx, pdf_path in enumerate(self.pdf_files):
                        name = pdf_path.name
                        # Check if this is an inbox PDF
                        is_inbox = self.inbox_dir and pdf_path.parent == self.inbox_dir
                        # Truncate long names, add inbox indicator
                        max_len = 50 if is_inbox else 60
                        display_name = name if len(name) <= max_len else name[:max_len - 3] + "..."
                        if is_inbox:
                            display_name = f"[new] {display_name}"
                        yield Button(
                            display_name,
                            id=f"{self.BUTTON_PREFIX}select-{idx}",
                            variant="primary" if str(pdf_path) == self.current_pdf else "default",
                        )

            yield Label("")
            yield Button("Cancel", id=f"{self.BUTTON_PREFIX}cancel", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if not button_id or not button_id.startswith(self.BUTTON_PREFIX):
            return

        event.stop()
        action = button_id[len(self.BUTTON_PREFIX):]

        if action == "cancel":
            self.dismiss(None)
        elif action == "clear":
            self.dismiss("")  # Empty string means clear the link
        elif action.startswith("select-"):
            try:
                idx = int(action[7:])  # Remove "select-" prefix
                if 0 <= idx < len(self.pdf_files):
                    self.dismiss(str(self.pdf_files[idx]))
                    return
            except ValueError:
                pass
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
        align: left middle;
    }

    #stats-text {
        width: 1fr;
    }

    #filter-input {
        width: 30;
        background: #0d1117;
        border: solid #30363d;
    }

    #filter-input:focus {
        border: solid #58a6ff;
    }

    /* Papers table styling */
    #papers-table {
        height: 1fr;
        width: 100%;
        background: #0d1117;
        border: solid #30363d;
    }

    #papers-table:focus {
        border: solid #58a6ff;
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

    #detail-panel:focus-within {
        border: solid #58a6ff;
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

    #log-panel:focus-within {
        border: solid #58a6ff;
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

    /* Metadata mismatch dialog styling */
    #mismatch-dialog {
        width: 90;
        height: auto;
        max-height: 35;
        border: thick #d29922;
        background: #161b22;
        padding: 2;
        overflow-y: auto;
    }

    #mismatch-dialog Label {
        color: #c9d1d9;
    }

    #mismatch-dialog Button {
        margin: 0 1;
    }

    /* PDF chooser dialog styling */
    #pdf-dialog {
        width: 80;
        height: auto;
        max-height: 30;
        border: thick #58a6ff;
        background: #161b22;
        padding: 2;
    }

    #pdf-dialog Label {
        color: #c9d1d9;
    }

    #pdf-dialog Button {
        margin: 0 1 1 0;
        width: 100%;
    }

    #pdf-list {
        height: auto;
        max-height: 15;
        background: #0d1117;
        border: solid #30363d;
        padding: 1;
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
        Binding("n", "notes", "Notes"),
        Binding("u", "undo", "Undo"),
        # Paper actions
        Binding("o", "open", "Open URL/Scholar"),
        Binding("p", "open_pdf", "Open local PDF"),
        Binding("l", "link_pdf", "Link PDF"),
        Binding("d", "toggle_details", "Toggle details"),
        Binding("e", "enrich", "Enrich metadata"),
        # Project actions
        Binding("s", "snowball", "Run snowball"),
        Binding("x", "export", "Export"),
        Binding("f", "filter", "Filter papers"),
        Binding("g", "graph", "Generate graph"),
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

        # Keyword filter for title search
        self.filter_keyword: str = ""

        # Worker context for background tasks
        self._worker_context: dict = {}

        # Event log for tracking actions (display format and raw for file)
        # Uses append() for O(1) inserts, reversed for display (newest first)
        self._event_log: list[str] = []
        self._event_log_raw: list[str] = []
        self._event_log_dirty: bool = False  # Deferred save flag

        # Undo stack for status changes: (paper_id, previous_status, title)
        self._last_status_change: Optional[tuple[str, PaperStatus, str]] = None

        # Cached widget references for performance (set in on_mount)
        self._detail_content: Optional[Static] = None
        self._log_content: Optional[Static] = None

        # Cache for source paper titles (avoids N+1 lookups)
        self._source_title_cache: dict[str, str] = {}

        # Debounce timer for filter input
        self._filter_timer: Optional[object] = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="stats-panel"):
            yield Static(self._get_stats_text(), id="stats-text")
            yield Input(placeholder="Filter titles...", id="filter-input")
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
        # Cache widget references for performance (avoids repeated DOM queries)
        self._detail_content = self.query_one("#detail-content", Static)
        self._log_content = self.query_one("#log-content", Static)

        table = self.query_one("#papers-table", DataTable)

        # Add columns with sort indicators
        table.add_columns(
            self._get_column_label("Status"),
            self._get_column_label("Title"),
            self._get_column_label("Year"),
            self._get_column_label("Refs"),
            self._get_column_label("Cite"),
            self._get_column_label("Obs"),
            self._get_column_label("Source"),
            self._get_column_label("Iter"),
            "PDF",
        )

        # Load and display papers
        self._refresh_table()

        # Load existing event log from file
        self._load_event_log()

        # Update log panel with loaded entries (using cached reference)
        if self._event_log and self._log_content:
            self._log_content.update("\n".join(self._event_log))

        # Log startup
        stats = self.storage.get_statistics()
        self._log_event(f"[#58a6ff]Loaded:[/#58a6ff] {stats['total']} papers")

        # Show first paper's details if available
        papers = self.storage.load_all_papers()
        if papers:
            self._show_paper_details(papers[0])

        # Focus the table by default
        table.focus()

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
            self._get_column_label("Refs"),
            self._get_column_label("Cite"),
            self._get_column_label("Obs"),
            self._get_column_label("Source"),
            self._get_column_label("Iter"),
            "PDF",
        )

        papers = self.storage.load_all_papers()

        # Apply status filter if set
        if self.filter_status is not None:
            papers = [p for p in papers if p.status == self.filter_status]

        # Apply keyword filter if set
        if self.filter_keyword:
            keyword_lower = self.filter_keyword.lower()
            papers = [p for p in papers if keyword_lower in p.title.lower()]

        # Sort papers using current sort settings
        papers.sort(key=self._get_sort_key, reverse=not self.sort_ascending)

        for paper in papers:
            # Status indicator with icon and text
            status_val = get_status_value(paper.status)
            status_display = {
                "included": "[#3fb950]✓ Included[/#3fb950]",
                "excluded": "[#f85149]✗ Excluded[/#f85149]",
                "pending": "[#d29922]? Pending[/#d29922]",
            }.get(status_val, "?")

            # Title (truncate for readability)
            title = truncate_title(paper.title, max_length=140)

            # Citations
            citations = str(paper.citation_count) if paper.citation_count is not None else "-"

            # Source
            source = get_source_value(paper.source)
            source_short = {"seed": "Seed", "backward": "Bkd", "forward": "Fwd"}.get(source, source)

            # PDF indicator
            pdf_indicator = "[#58a6ff]pdf[/#58a6ff]" if paper.pdf_path else ""

            # Observation count
            obs_count = str(paper.observation_count) if paper.observation_count > 1 else ""

            # GROBID references count
            grobid_refs = paper.raw_data.get("grobid_references", []) if paper.raw_data else []
            refs_count = str(len(grobid_refs)) if grobid_refs else ""

            # Year with color for out-of-range values
            if paper.year:
                year_excluded = False
                if self.project.filter_criteria.min_year and paper.year < self.project.filter_criteria.min_year:
                    year_excluded = True
                if self.project.filter_criteria.max_year and paper.year > self.project.filter_criteria.max_year:
                    year_excluded = True
                year_display = f"[#f85149]{paper.year}[/#f85149]" if year_excluded else str(paper.year)
            else:
                year_display = "-"

            table.add_row(
                status_display,
                title,
                year_display,
                refs_count,
                citations,
                obs_count,
                source_short,
                str(paper.snowball_iteration),
                pdf_indicator,
                key=paper.id,
            )

        # Update stats
        stats_panel = self.query_one("#stats-text", Static)
        stats_panel.update(self._get_stats_text())

    def _get_stats_text(self) -> str:
        """Get statistics text."""
        stats = self.storage.get_statistics()
        total = stats["total"]
        by_status = stats.get("by_status", {})

        included = by_status.get("included", 0)
        excluded = by_status.get("excluded", 0)
        pending = by_status.get("pending", 0)

        # Filter indicator
        if self.filter_status is None:
            filter_text = "[bold]Filter:[/bold] All"
        elif self.filter_status == PaperStatus.PENDING:
            filter_text = "[bold]Filter:[/bold] [#d29922]Pending[/#d29922]"
        elif self.filter_status == PaperStatus.INCLUDED:
            filter_text = "[bold]Filter:[/bold] [#3fb950]Included[/#3fb950]"
        elif self.filter_status == PaperStatus.EXCLUDED:
            filter_text = "[bold]Filter:[/bold] [#f85149]Excluded[/#f85149]"
        else:
            filter_text = "[bold]Filter:[/bold] All"

        return (
            f"[bold #58a6ff]{self.project.name}[/bold #58a6ff] [dim]│[/dim] "
            f"[bold]Total:[/bold] [#58a6ff]{total}[/#58a6ff] [dim]│[/dim] "
            f"[#3fb950]✓ {included}[/#3fb950] [dim]│[/dim] "
            f"[#f85149]✗ {excluded}[/#f85149] [dim]│[/dim] "
            f"[#d29922]? {pending}[/#d29922] [dim]│[/dim] "
            f"{filter_text} [dim]│[/dim] "
            f"[bold]Iter:[/bold] [#a371f7]{self.project.current_iteration}[/#a371f7]"
        )

    def _format_paper_details(self, paper: Paper) -> str:
        """Format paper details as rich text using shared function."""
        details = format_paper_rich(paper)

        # Add connections (source papers that led to this discovery)
        if paper.source_paper_ids:
            connections = []
            for source_id in paper.source_paper_ids:
                # Use cached title or load and cache
                if source_id in self._source_title_cache:
                    title = self._source_title_cache[source_id]
                else:
                    source_paper = self.storage.load_paper(source_id)
                    if source_paper:
                        title = source_paper.title
                        self._source_title_cache[source_id] = title
                    else:
                        title = None

                if title:
                    # Truncate long titles
                    if len(title) > 80:
                        title = title[:77] + "..."
                    connections.append(f"  • {title}")

            if connections:
                details += "\n\n[bold #79c0ff]Discovered via:[/bold #79c0ff]"
                details += "\n" + "\n".join(connections)

        return details

    def _show_paper_details(self, paper: Paper) -> None:
        """Show details for a paper in the detail panel."""
        self.current_paper = paper
        details_text = self._format_paper_details(paper)

        # Update the content using cached reference (avoids DOM query on every call)
        if self._detail_content:
            self._detail_content.update(details_text)

    def _log_event(self, message: str) -> None:
        """Add an event to the log panel (async file save)."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Store with full timestamp for file, display with short timestamp
        display_entry = f"[dim]{timestamp[11:]}[/dim] {message}"
        file_entry = f"{timestamp} {message}"

        # Append for O(1) performance (display reversed for newest-first)
        self._event_log.append(display_entry)
        self._event_log_raw.append(file_entry)

        # Keep only last 100 entries (trim from front - oldest)
        if len(self._event_log) > 100:
            self._event_log = self._event_log[-100:]
            self._event_log_raw = self._event_log_raw[-100:]

        # Mark dirty for deferred save (saved on quit)
        self._event_log_dirty = True

        # Update the log panel (reversed for newest-first display)
        if self._log_content:
            self._log_content.update("\n".join(reversed(self._event_log)))

    def _load_event_log(self) -> None:
        """Load event log from file (stored newest first, converted to oldest first for append)."""
        logs_dir = self.project_dir / "logs"
        logs_dir.mkdir(exist_ok=True)
        log_file = logs_dir / "event_log.txt"
        self._event_log = []
        self._event_log_raw = []

        if log_file.exists():
            try:
                with open(log_file, "r") as f:
                    lines = f.read().strip().split("\n")
                    # Keep first 100 entries (newest first in file)
                    lines = lines[:100] if len(lines) > 100 else lines
                    # Reverse to get oldest-first order (for append-based storage)
                    for line in reversed(lines):
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
        """Save event log to file (newest first for conventional log format)."""
        logs_dir = self.project_dir / "logs"
        logs_dir.mkdir(exist_ok=True)
        log_file = logs_dir / "event_log.txt"
        try:
            # Write newest-first (reverse of internal oldest-first list)
            with open(log_file, "w") as f:
                f.write("\n".join(reversed(self._event_log_raw)))
            self._event_log_dirty = False
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

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle filter input changes with debouncing."""
        if event.input.id == "filter-input":
            # Cancel any pending filter timer
            if self._filter_timer is not None:
                self._filter_timer.stop()

            # Store the value immediately for responsiveness
            self.filter_keyword = event.value

            # Debounce: wait 100ms before refreshing table
            self._filter_timer = self.set_timer(0.1, self._apply_filter)

    def _apply_filter(self) -> None:
        """Apply the current filter (called after debounce delay)."""
        self._filter_timer = None
        self._refresh_table()

        # Move cursor to first row if there are results
        table = self.query_one("#papers-table", DataTable)
        if table.row_count > 0:
            table.move_cursor(row=0)

    def _update_paper_status(self, status: PaperStatus) -> None:
        """Update the status of the currently selected paper and stay on next."""
        if not self.current_paper:
            return

        # Save for undo before changing (convert status string to enum if needed)
        current_status = self.current_paper.status
        if isinstance(current_status, str):
            current_status = PaperStatus(current_status)
        self._last_status_change = (
            self.current_paper.id,
            current_status,
            self.current_paper.title,
        )

        # Get the current table position
        table = self.query_one("#papers-table", DataTable)
        current_row_index = table.cursor_row

        # Log the status change
        status_labels = {
            PaperStatus.INCLUDED: "[#3fb950]Included:[/#3fb950]",
            PaperStatus.EXCLUDED: "[#f85149]Excluded:[/#f85149]",
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

            # Immediately show details for the new current paper
            # (don't wait for async on_data_table_row_highlighted event)
            coord = Coordinate(target_row, 0)
            row_key, _ = table.coordinate_to_cell_key(coord)
            if row_key:
                paper = self.storage.load_paper(row_key.value)
                if paper:
                    self._show_paper_details(paper)

    def action_include(self) -> None:
        """Mark the selected paper as included."""
        self._update_paper_status(PaperStatus.INCLUDED)

    def action_exclude(self) -> None:
        """Mark the selected paper as excluded."""
        self._update_paper_status(PaperStatus.EXCLUDED)

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
        """Open the paper's DOI, arXiv URL, or search Google Scholar."""
        if not self.current_paper:
            return

        # Prefer DOI, then arXiv, fallback to Google Scholar search
        if self.current_paper.doi:
            url = f"https://doi.org/{self.current_paper.doi}"
        elif self.current_paper.arxiv_id:
            url = f"https://arxiv.org/abs/{self.current_paper.arxiv_id}"
        else:
            # No identifier - search Google Scholar by title
            query = quote_plus(self.current_paper.title)
            url = f"https://scholar.google.com/scholar?q={query}"

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

    def action_link_pdf(self) -> None:
        """Link a PDF file to the current paper.

        Shows PDFs from inbox/ (unmatched) first, then pdfs/ (already matched).
        PDFs linked from inbox are moved to pdfs/ folder.
        """
        if not self.current_paper:
            return

        # Get list of PDFs from both inbox and pdfs folders
        pdfs_dir = self.project_dir / "pdfs"
        inbox_dir = pdfs_dir / "inbox"
        pdfs_dir.mkdir(exist_ok=True)
        inbox_dir.mkdir(exist_ok=True)

        # Inbox PDFs first (these need linking), then already-matched PDFs
        inbox_files = sorted(inbox_dir.glob("*.pdf"))
        matched_files = sorted(pdfs_dir.glob("*.pdf"))
        pdf_files = inbox_files + matched_files

        def handle_selection(result: Optional[str]) -> None:
            if result is None:
                return  # Cancelled

            if result == "":
                # Clear the link
                self.current_paper.pdf_path = None
                self.storage.save_paper(self.current_paper)
                self._log_event(f"[dim]Unlinked PDF from:[/dim] {self.current_paper.title}")
                self.notify("PDF link cleared", severity="information")
                self._show_paper_details(self.current_paper)
                self._refresh_table()
            else:
                import shutil
                selected_path = Path(result)
                pdf_name = selected_path.name

                # If PDF is in inbox, move it to pdfs/
                if selected_path.parent == inbox_dir:
                    new_path = pdfs_dir / pdf_name
                    shutil.move(str(selected_path), str(new_path))
                    final_path = str(new_path)
                    self._log_event(f"[#58a6ff]Linked & moved:[/#58a6ff] {pdf_name}")
                else:
                    final_path = result
                    self._log_event(f"[#58a6ff]Linked:[/#58a6ff] {pdf_name} → {truncate_title(self.current_paper.title, 40)}")

                # Set the link
                self.current_paper.pdf_path = final_path
                self.storage.save_paper(self.current_paper)
                self.notify(f"Extracting references from PDF...", timeout=60)

                # Store context for worker
                self._worker_context["link_pdf"] = {
                    "paper_id": self.current_paper.id,
                    "pdf_path": final_path,
                    "pdf_name": pdf_name,
                }

                def do_parse() -> dict:
                    """Parse the linked PDF with GROBID in background."""
                    pdf_parser = PDFParser()
                    try:
                        parse_result = pdf_parser.parse(Path(final_path))
                        return {
                            "success": True,
                            "references": parse_result.references if parse_result else [],
                        }
                    except Exception as e:
                        return {"success": False, "error": str(e), "references": []}

                self.run_worker(do_parse, name="link_pdf", thread=True)

                # Refresh display immediately (references will update when worker completes)
                self._show_paper_details(self.current_paper)
                self._refresh_table()

        self.push_screen(
            PDFChooserDialog(pdf_files, self.current_paper.pdf_path, inbox_dir),
            handle_selection
        )

    def action_snowball(self) -> None:
        """Run a snowball iteration."""
        # Store context
        old_count = len(self.storage.load_all_papers())
        self._worker_context["snowball"] = {"old_count": old_count}

        # Show working notification
        self.notify("Running snowball...", timeout=60)

        def do_snowball() -> dict:
            """Run snowball in background thread."""
            result = self.engine.run_snowball_iteration(self.project)
            return result

        self.run_worker(do_snowball, name="snowball", thread=True)

    def _handle_snowball_complete(self) -> None:
        """Handle snowball worker completion."""
        ctx = self._worker_context.get("snowball", {})
        old_count = ctx.get("old_count", 0)
        worker_result = ctx.get("worker_result", {})

        self.project = self.storage.load_project()
        new_count = len(self.storage.load_all_papers())
        new_papers = new_count - old_count

        # Get merged papers from result
        merged_papers = worker_result.get("merged_papers", []) if isinstance(worker_result, dict) else []
        merged_count = len(merged_papers)

        self._refresh_table()

        # Log merged papers first
        for paper in merged_papers:
            self._log_event(f"[#d29922]Merged:[/#d29922] {paper.title}")

        if new_papers > 0 or merged_count > 0:
            msg_parts = []
            if new_papers > 0:
                msg_parts.append(f"+{new_papers} new")
            if merged_count > 0:
                msg_parts.append(f"{merged_count} merged")
            msg = ", ".join(msg_parts)
            self.notify(f"Found {msg}", title="Snowball complete", severity="information")
            self._log_event(f"[#a371f7]Snowball:[/#a371f7] iteration {self.project.current_iteration}, {msg}")
        else:
            self.notify("No new papers found", title="Snowball complete", severity="warning")
            self._log_event(f"[#a371f7]Snowball:[/#a371f7] iteration {self.project.current_iteration}, no new papers")

    def action_export(self) -> None:
        """Export papers to BibTeX, CSV, TikZ, and PNG graph."""
        from ..visualization import generate_citation_graph

        papers = self.storage.load_all_papers()
        included_count = sum(1 for p in papers if p.status == PaperStatus.INCLUDED)

        # Create output directory
        output_dir = self.project_dir / "output"
        output_dir.mkdir(exist_ok=True)

        # Export BibTeX
        bibtex_exporter = BibTeXExporter()
        bibtex_content = bibtex_exporter.export(papers, only_included=True)
        bibtex_path = output_dir / "included_papers.bib"
        with open(bibtex_path, "w") as f:
            f.write(bibtex_content)

        # Export CSV
        csv_exporter = CSVExporter()
        csv_path = output_dir / "all_papers.csv"
        csv_exporter.export(papers, csv_path, only_included=False)

        # Export TikZ (both embeddable and standalone versions)
        tikz_exporter = TikZExporter()

        tikz_content = tikz_exporter.export(papers, only_included=True, standalone=False)
        tikz_path = output_dir / "citation_graph.tex"
        with open(tikz_path, "w") as f:
            f.write(tikz_content)

        tikz_standalone = tikz_exporter.export(papers, only_included=True, standalone=True)
        tikz_standalone_path = output_dir / "citation_graph_standalone.tex"
        with open(tikz_standalone_path, "w") as f:
            f.write(tikz_standalone)

        # Export PNG graph
        graph_path = generate_citation_graph(
            papers=papers,
            output_dir=output_dir,
            title=self.project.name,
        )

        if graph_path:
            self.notify("Exported BibTeX, CSV, TikZ, and graph", title="Export complete", severity="information")
            self._log_event(f"[#d29922]Exported:[/#d29922] {included_count} included → BibTeX, CSV, TikZ, PNG")
        else:
            self.notify("Exported BibTeX, CSV, and TikZ", title="Export complete", severity="information")
            self._log_event(f"[#d29922]Exported:[/#d29922] {included_count} included → BibTeX, CSV, TikZ")

    def action_graph(self) -> None:
        """Generate citation network graph visualization."""
        from ..visualization import generate_citation_graph

        papers = self.storage.load_all_papers()

        if not papers:
            self.notify("No papers to visualize", severity="warning")
            return

        # Output to output/ folder in project directory
        output_dir = self.project_dir / "output"
        output_dir.mkdir(exist_ok=True)

        self.notify("Generating graph...", title="Please wait")

        output_path = generate_citation_graph(
            papers=papers,
            output_dir=output_dir,
            title=f"{self.project.name} - Citation Network",
        )

        if output_path:
            self.notify(
                f"Saved to {output_path.name}",
                title="Graph generated",
                severity="information",
            )
            self._log_event(f"[#58a6ff]Graph:[/#58a6ff] {output_path.name} ({len(papers)} papers)")
        else:
            self.notify(
                "Install viz dependencies: pip install snowball-slr[viz]",
                title="Missing dependencies",
                severity="error",
            )

    def action_filter(self) -> None:
        """Cycle through filter states: all → pending → included → excluded → all."""
        # Define the cycle order
        cycle = [None, PaperStatus.PENDING, PaperStatus.INCLUDED, PaperStatus.EXCLUDED]

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
        """Scan pdfs/inbox/ folder and parse PDFs, matching to papers by title.

        Matched PDFs are moved from inbox/ to pdfs/ folder.
        Unmatched PDFs remain in inbox/ for manual linking.
        """
        pdfs_dir = self.project_dir / "pdfs"
        inbox_dir = pdfs_dir / "inbox"

        # Create directories if needed
        pdfs_dir.mkdir(exist_ok=True)
        inbox_dir.mkdir(exist_ok=True)

        pdf_files = list(inbox_dir.glob("*.pdf"))
        if not pdf_files:
            self.notify("No PDFs in pdfs/inbox/ folder", severity="warning")
            return

        # Store context
        self._worker_context["parse_pdfs"] = {"pdf_files": pdf_files, "pdfs_dir": pdfs_dir}

        # Show working notification
        self.notify(f"Parsing {len(pdf_files)} PDFs from inbox...", timeout=60)

        def do_parse() -> dict:
            """Parse PDFs in background thread."""
            import shutil
            all_papers = self.storage.load_all_papers()
            pdf_parser = PDFParser()

            processed = 0
            no_match = 0

            for pdf_path in pdf_files:
                try:
                    result = pdf_parser.parse(pdf_path)
                    if not result.title:
                        no_match += 1
                        continue

                    # Find matching paper by title (fuzzy match)
                    matched_paper = self._find_paper_by_title_fuzzy(all_papers, result.title)

                    if matched_paper:
                        # Move PDF from inbox to pdfs/
                        new_path = pdfs_dir / pdf_path.name
                        shutil.move(str(pdf_path), str(new_path))

                        # Store references
                        if result.references:
                            if matched_paper.raw_data is None:
                                matched_paper.raw_data = {}
                            matched_paper.raw_data["grobid_references"] = result.references

                        matched_paper.pdf_path = str(new_path)
                        self.storage.save_paper(matched_paper)
                        processed += 1
                    else:
                        no_match += 1

                except Exception:
                    no_match += 1  # Count failed parses as no match

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

        # Store context for worker completion handler, including original values for sanity check
        self._worker_context["enrich"] = {
            "paper": paper,
            "had_abstract": bool(paper.abstract),
            "had_year": paper.year is not None,
            "had_citations": paper.citation_count is not None,
            "had_doi": bool(paper.doi),
            "cursor_row": current_row_index,
            # Save original values for sanity checking
            "original_title": paper.title,
            "original_year": paper.year,
            "original_authors": [a.name for a in paper.authors] if paper.authors else [],
        }

        # Show working notification
        self.notify("Enriching metadata...", timeout=30)

        def do_enrich() -> dict:
            """Run enrichment in background thread."""
            # First, enrich metadata as usual
            self.engine.api.enrich_metadata(paper)

            # If paper has a DOI, fetch the authoritative data for that DOI
            # to compare against current title (GROBID might have extracted wrong title)
            doi_paper = None
            if paper.doi:
                doi_paper = self.engine.api.search_by_doi(paper.doi)

            return {"doi_paper": doi_paper}

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
            # Store worker result in context for handler
            if hasattr(event.worker, 'result') and event.worker.result:
                self._worker_context["enrich"]["worker_result"] = event.worker.result
            self._handle_enrich_complete()
        elif worker_name == "snowball":
            # Store worker result in context for handler
            if hasattr(event.worker, 'result') and event.worker.result:
                self._worker_context["snowball"]["worker_result"] = event.worker.result
            self._handle_snowball_complete()
        elif worker_name == "parse_pdfs":
            self._handle_parse_pdfs_complete()
        elif worker_name == "link_pdf":
            # Store worker result in context for handler
            if hasattr(event.worker, 'result') and event.worker.result:
                self._worker_context["link_pdf"]["worker_result"] = event.worker.result
            self._handle_link_pdf_complete()

    def _handle_link_pdf_complete(self) -> None:
        """Handle link PDF worker completion - store extracted references."""
        ctx = self._worker_context.get("link_pdf", {})
        paper_id = ctx.get("paper_id")
        pdf_name = ctx.get("pdf_name", "PDF")
        worker_result = ctx.get("worker_result", {})

        if not paper_id:
            return

        # Get the paper (may have been updated in the meantime)
        paper = self.storage.load_paper(paper_id)
        if not paper:
            return

        references = worker_result.get("references", [])
        success = worker_result.get("success", False)

        if success and references:
            # Store extracted references
            if paper.raw_data is None:
                paper.raw_data = {}
            paper.raw_data["grobid_references"] = references
            self.storage.save_paper(paper)

            self._log_event(
                f"[#3fb950]Extracted {len(references)} refs[/#3fb950] from {pdf_name}"
            )
            self.notify(f"Extracted {len(references)} references", severity="information")
        elif success:
            self._log_event(f"[dim]No references found in {pdf_name}[/dim]")
            self.notify(f"Linked: {pdf_name} (no references found)", severity="information")
        else:
            error = worker_result.get("error", "Unknown error")
            self._log_event(f"[#f85149]Parse failed:[/#f85149] {error[:50]}")
            self.notify(f"Linked: {pdf_name} (parse failed)", severity="warning")

        # Refresh details panel if still viewing the same paper
        if self.current_paper and self.current_paper.id == paper_id:
            # Reload to get updated references
            self.current_paper = paper
            self._show_paper_details(paper)

    def _handle_enrich_complete(self) -> None:
        """Handle enrich worker completion."""
        ctx = self._worker_context.get("enrich", {})
        paper = ctx.get("paper")

        if not paper:
            return

        # Get the DOI paper lookup result (if available)
        worker_result = ctx.get("worker_result", {})
        doi_paper = worker_result.get("doi_paper") if isinstance(worker_result, dict) else None

        # Check for mismatches
        mismatches = []
        original_title = ctx.get("original_title", "")
        original_year = ctx.get("original_year")

        # If we have a DOI and fetched the authoritative data, compare against that
        # This catches cases where GROBID extracted wrong title but DOI is correct
        if doi_paper and doi_paper.title:
            if not titles_match(paper.title, doi_paper.title):
                mismatches.append(("Title", paper.title, doi_paper.title))
                self._worker_context["enrich"]["enriched_title"] = doi_paper.title

            # Also check year from DOI lookup
            if doi_paper.year and paper.year and doi_paper.year != paper.year:
                mismatches.append(("Year", str(paper.year), str(doi_paper.year)))
                self._worker_context["enrich"]["enriched_year"] = doi_paper.year
            elif doi_paper.year and not paper.year:
                # DOI has year but paper doesn't - not a mismatch, just missing data
                paper.year = doi_paper.year

        # Fallback: check if enrichment changed values (for papers without DOI)
        elif paper.title and original_title and paper.title != original_title:
            if not titles_match(original_title, paper.title):
                mismatches.append(("Title", original_title, paper.title))
                self._worker_context["enrich"]["enriched_title"] = paper.title
                # Restore original until user approves
                paper.title = original_title

        # Year mismatch from enrichment (if not already checked via DOI)
        if not doi_paper and original_year is not None and paper.year is not None and original_year != paper.year:
            mismatches.append(("Year", str(original_year), str(paper.year)))
            self._worker_context["enrich"]["enriched_year"] = paper.year
            # Restore original until user approves
            paper.year = original_year

        # If mismatches found, show dialog for user to approve/reject
        if mismatches:
            self._worker_context["enrich"]["mismatches"] = mismatches
            self.push_screen(MetadataMismatchDialog(mismatches, doi=paper.doi), self._on_mismatch_dialog_result)
            return

        # No mismatches - proceed normally
        self._finalize_enrich(paper, ctx)

    def _on_mismatch_dialog_result(self, selections: Optional[dict]) -> None:
        """Handle the result from the metadata mismatch dialog."""
        ctx = self._worker_context.get("enrich", {})
        paper = ctx.get("paper")

        if not paper or selections is None:
            # Dialog cancelled - save paper with original values restored
            self.storage.save_paper(paper)
            self._finalize_enrich(paper, ctx, cancelled=True)
            return

        # Apply approved changes
        applied = []
        if selections.get("Title"):
            paper.title = ctx.get("enriched_title", paper.title)
            applied.append("Title")
        if selections.get("Year"):
            paper.year = ctx.get("enriched_year", paper.year)
            applied.append("Year")

        # Save and finalize
        self.storage.save_paper(paper)

        if applied:
            self._log_event(f"[#d29922]Updated:[/#d29922] {paper.title} ({', '.join(applied)} from API)")

        self._finalize_enrich(paper, ctx)

    def _finalize_enrich(self, paper: Paper, ctx: dict, cancelled: bool = False) -> None:
        """Finalize the enrich operation - save, notify, refresh."""
        # Save the paper
        self.storage.save_paper(paper)

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

        if cancelled:
            self.notify("Enrichment cancelled - kept original values", severity="warning")
            self._log_event(f"[#58a6ff]Enriched:[/#58a6ff] {paper.title} (cancelled)")
        elif updates:
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
  n           Add/edit notes
  u           Undo last status change

[bold]Paper Actions:[/bold]
  o           Open DOI/arXiv in browser
  p           Open local PDF
  l           Link/unlink PDF to paper
  e           Enrich metadata from APIs

[bold]Table:[/bold]
  Click header Sort by column (cycles: asc → desc → default)

[bold]Project Actions:[/bold]
  s           Run snowball iteration
  x           Export papers (BibTeX + CSV)
  f           Filter papers (cycles: all → pending → included → excluded)
  g           Generate citation graph (600 DPI PNG)
  P           Parse PDFs in pdfs/ folder (Shift+P)

[bold]Other:[/bold]
  Ctrl+P      Command palette
  ?           Show this help
  q           Quit

Press any key to close this help.
"""
        self.notify(help_text, title="Help", timeout=30)

    def action_quit(self) -> None:
        """Quit the application, ensuring all pending writes are flushed."""
        # Save event log if dirty
        if self._event_log_dirty:
            self._save_event_log()

        # Flush any pending disk writes before exiting
        self.storage.shutdown()
        self.exit()


def run_tui(
    project_dir: Path, storage: JSONStorage, engine: SnowballEngine, project: ReviewProject
) -> None:
    """Run the TUI application."""
    app = SnowballApp(project_dir, storage, engine, project)
    app.run()
