"""Modal dialogs for the Snowball TUI."""

from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Select, TextArea

from ..models import Paper
from ..paper_utils import get_status_value, truncate_title


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
            self.dismiss((status_widget.value, notes_widget.text))
        else:
            self.dismiss(None)


class MetadataMismatchDialog(ModalScreen[Optional[dict]]):
    """Dialog to show metadata mismatches and let user approve/reject changes."""

    BUTTON_PREFIX = "mismatch-"

    def __init__(self, mismatches: list[tuple[str, str, str]], doi: str = None):
        super().__init__()
        self.mismatches = mismatches
        self.doi = doi
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
                current_display = current[:100] + ("..." if len(current) > 100 else "")
                api_display = api_val[:100] + ("..." if len(api_val) > 100 else "")
                yield Label(f"  [dim]PDF/Current:[/dim] {current_display}")
                yield Label(f"  [#58a6ff]API/DOI:[/#58a6ff] {api_display}")
                yield Button(f"Use API {field}", id=f"{self.BUTTON_PREFIX}update-{field}", variant="primary")
                yield Label("")

            with Horizontal():
                yield Button("Keep Current", variant="default", id=f"{self.BUTTON_PREFIX}done")
                if self.doi:
                    yield Button("Trust DOI (Update All)", variant="success", id=f"{self.BUTTON_PREFIX}update-all")
                else:
                    yield Button("Use All API Values", variant="warning", id=f"{self.BUTTON_PREFIX}update-all")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if not button_id or not button_id.startswith(self.BUTTON_PREFIX):
            return

        event.stop()
        action = button_id[len(self.BUTTON_PREFIX):]

        if action == "done":
            self.dismiss(self.field_choices)
        elif action == "update-all":
            for field, _, _ in self.mismatches:
                self.field_choices[field] = True
            self.dismiss(self.field_choices)
        elif action.startswith("update-"):
            field = action[7:]
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
                with ScrollableContainer(id="pdf-list"):
                    for idx, pdf_path in enumerate(self.pdf_files):
                        name = pdf_path.name
                        is_inbox = self.inbox_dir and pdf_path.parent == self.inbox_dir
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
            self.dismiss("")
        elif action.startswith("select-"):
            try:
                idx = int(action[7:])
                if 0 <= idx < len(self.pdf_files):
                    self.dismiss(str(self.pdf_files[idx]))
                    return
            except ValueError:
                pass
            self.dismiss(None)


class RelevanceMethodDialog(ModalScreen[Optional[str]]):
    """Dialog to choose relevance scoring method."""

    BUTTON_PREFIX = "rel-"

    def compose(self) -> ComposeResult:
        with Container(id="relevance-dialog"):
            yield Label("[bold #58a6ff]Compute Relevance Scores[/bold #58a6ff]\n")
            yield Label("[dim]Choose scoring method:[/dim]\n")

            yield Button(
                "TF-IDF (fast, offline)",
                id=f"{self.BUTTON_PREFIX}tfidf",
                variant="primary",
            )
            yield Button(
                "LLM (OpenAI API)",
                id=f"{self.BUTTON_PREFIX}llm",
                variant="default",
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
        elif action in ("tfidf", "llm"):
            self.dismiss(action)
