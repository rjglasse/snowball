"""Project setup TUI."""

from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, ScrollableContainer
from textual.widgets import Button, Footer, Header, Input, Label, Select, Static
from textual.worker import Worker, WorkerState

from ..paper_utils import truncate_title
from ..services import (
    ProjectContext,
    add_seed_dois,
    add_seed_pdfs,
    create_project,
    load_project,
)


class ProjectSetupApp(App[Optional[ProjectContext]]):
    """Startup TUI for creating/opening a project and adding seed papers."""

    TITLE = "Snowball SLR"
    SUB_TITLE = "Project Setup"

    CSS = """
    Screen {
        background: #0a0e14;
    }

    #setup-root {
        padding: 1 2;
        height: 100%;
    }

    .setup-section {
        border: solid #30363d;
        padding: 1;
        margin-bottom: 1;
        background: #0d1117;
    }

    .setup-title {
        color: #58a6ff;
        text-style: bold;
        margin-bottom: 1;
    }

    .setup-log {
        min-height: 7;
        border: solid #30363d;
        background: #0d1117;
        color: #c9d1d9;
        padding: 1;
    }

    Label {
        color: #c9d1d9;
        text-style: bold;
    }

    Input {
        margin-bottom: 1;
        background: #0d1117;
        border: solid #30363d;
    }

    Input:focus {
        border: solid #58a6ff;
    }

    Select {
        margin-bottom: 1;
        background: #0d1117;
        border: solid #30363d;
    }

    Button {
        margin-right: 1;
        background: #21262d;
        color: #c9d1d9;
        border: solid #30363d;
    }

    Button:hover {
        background: #30363d;
        border: solid #58a6ff;
    }

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
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, initial_directory: Optional[Path] = None):
        super().__init__()
        self.initial_directory = initial_directory
        self.context: Optional[ProjectContext] = None
        self._setup_log: list[str] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(id="setup-root"):
            yield Static("Snowball Project Setup", classes="setup-title")

            with Container(classes="setup-section"):
                yield Label("Project")
                yield Input(
                    value=str(self.initial_directory) if self.initial_directory else "",
                    placeholder="Project directory",
                    id="setup-project-dir",
                )
                yield Input(placeholder="Project name", id="setup-project-name")
                yield Input(placeholder="Description", id="setup-project-description")
                yield Input(placeholder="Research question", id="setup-research-question")
                with Horizontal():
                    yield Input(placeholder="Min year", id="setup-min-year")
                    yield Input(placeholder="Max year", id="setup-max-year")
                with Horizontal():
                    yield Button("Create Project", id="setup-create", variant="primary")
                    yield Button("Open Project", id="setup-open", variant="default")
                    yield Button("Start Review", id="setup-start", variant="success")

            with Container(classes="setup-section"):
                yield Label("Seed Papers")
                yield Select(
                    [
                        ("LLM extraction", "llm"),
                        ("GROBID", "grobid"),
                    ],
                    value="llm",
                    id="setup-extract",
                )
                yield Input(placeholder="PDF paths, separated by commas", id="setup-pdfs")
                yield Input(placeholder="DOIs, separated by commas", id="setup-dois")
                with Horizontal():
                    yield Button("Add PDF Seeds", id="setup-add-pdfs", variant="primary")
                    yield Button("Add DOI Seeds", id="setup-add-dois", variant="primary")

            yield Static("", id="setup-status", classes="setup-log")
        yield Footer()

    def on_mount(self) -> None:
        if self.initial_directory:
            self._log(f"Ready to open: {self.initial_directory}")
        else:
            self._log("Create or open a project.")

    def _log(self, message: str) -> None:
        self._setup_log.insert(0, message)
        self._setup_log = self._setup_log[:12]
        try:
            self.query_one("#setup-status", Static).update("\n".join(self._setup_log))
        except Exception:
            pass

    def _project_dir(self) -> Path:
        value = self.query_one("#setup-project-dir", Input).value.strip()
        if not value:
            raise ValueError("Project directory is required")
        return Path(value).expanduser()

    def _optional_int(self, widget_id: str) -> Optional[int]:
        value = self.query_one(widget_id, Input).value.strip()
        if not value:
            return None
        return int(value)

    def _extract_method(self) -> str:
        value = self.query_one("#setup-extract", Select).value
        return str(value or "llm")

    def _load_context(self, project_dir: Path, extraction_method: Optional[str] = None) -> ProjectContext:
        context = load_project(
            project_dir,
            extraction_method=extraction_method or self._extract_method(),
        )
        self.context = context
        return context

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "setup-create":
            self._handle_create_project()
        elif button_id == "setup-open":
            self._handle_open_project()
        elif button_id == "setup-add-pdfs":
            self._handle_add_pdfs()
        elif button_id == "setup-add-dois":
            self._handle_add_dois()
        elif button_id == "setup-start":
            self._handle_start_review()

    def _handle_create_project(self) -> None:
        try:
            context = create_project(
                self._project_dir(),
                name=self.query_one("#setup-project-name", Input).value.strip() or None,
                description=self.query_one("#setup-project-description", Input).value.strip() or None,
                min_year=self._optional_int("#setup-min-year"),
                max_year=self._optional_int("#setup-max-year"),
                research_question=self.query_one("#setup-research-question", Input).value.strip() or None,
            )
            context = self._load_context(context.project_dir)
            self._log(f"Created project: {context.project.name}")
            self._log(f"PDF extraction: {self._extract_method().upper()}")
        except Exception as e:
            self._log(f"Create failed: {e}")
            self.notify(str(e), title="Create failed", severity="error")

    def _handle_open_project(self) -> None:
        try:
            context = self._load_context(self._project_dir())
            self._log(f"Opened project: {context.project.name}")
            self._log(f"PDF extraction: {self._extract_method().upper()}")
        except Exception as e:
            self._log(f"Open failed: {e}")
            self.notify(str(e), title="Open failed", severity="error")

    def _ensure_context(self) -> ProjectContext:
        if self.context is None:
            return self._load_context(self._project_dir())
        return self.context

    def _handle_add_pdfs(self) -> None:
        try:
            context = self._ensure_context()
            paths = [
                p.strip()
                for p in self.query_one("#setup-pdfs", Input).value.split(",")
                if p.strip()
            ]
            if not paths:
                raise ValueError("Enter at least one PDF path")

            context = self._load_context(context.project_dir, self._extract_method())
            self.notify(f"Adding {len(paths)} PDF seed(s)...", timeout=120)

            def do_import() -> dict:
                result = add_seed_pdfs(context, paths)
                return {
                    "added": [paper.title for paper in result.added],
                    "skipped": result.skipped,
                    "count": len(result.added),
                }

            self.run_worker(do_import, name="setup_add_pdfs", thread=True)
        except Exception as e:
            self._log(f"PDF import failed: {e}")
            self.notify(str(e), title="PDF import failed", severity="error")

    def _handle_add_dois(self) -> None:
        try:
            context = self._ensure_context()
            dois = [
                d.strip()
                for d in self.query_one("#setup-dois", Input).value.split(",")
                if d.strip()
            ]
            if not dois:
                raise ValueError("Enter at least one DOI")

            self.notify(f"Adding {len(dois)} DOI seed(s)...", timeout=120)

            def do_import() -> dict:
                result = add_seed_dois(context, dois)
                return {
                    "added": [paper.title for paper in result.added],
                    "skipped": result.skipped,
                    "count": len(result.added),
                }

            self.run_worker(do_import, name="setup_add_dois", thread=True)
        except Exception as e:
            self._log(f"DOI import failed: {e}")
            self.notify(str(e), title="DOI import failed", severity="error")

    def _handle_start_review(self) -> None:
        try:
            context = self._ensure_context()
            self.exit(context)
        except Exception as e:
            self._log(f"Start failed: {e}")
            self.notify(str(e), title="Start failed", severity="error")

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.state != WorkerState.SUCCESS and event.state != WorkerState.ERROR:
            return

        self.clear_notifications()
        if event.state == WorkerState.ERROR:
            self._log(f"Import failed: {event.worker.error}")
            self.notify(str(event.worker.error), title="Import failed", severity="error")
            return

        result = event.worker.result if hasattr(event.worker, "result") else {}
        count = result.get("count", 0) if isinstance(result, dict) else 0
        skipped = result.get("skipped", []) if isinstance(result, dict) else []
        added = result.get("added", []) if isinstance(result, dict) else []

        self._log(f"Added {count} seed paper(s)")
        for title in added[:5]:
            self._log(f"Seed: {truncate_title(title, 70)}")
        for item in skipped[:5]:
            self._log(f"Skipped: {item}")
        self.notify(f"Added {count} seed paper(s)", severity="information")

    def action_quit(self) -> None:
        if self.context:
            self.context.storage.shutdown()
        self.exit(None)
