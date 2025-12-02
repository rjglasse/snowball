# Snowball SLR - Development Guide

## Project Overview

Snowball is a terminal-based Systematic Literature Review tool that uses snowballing methodology (backward/forward citation traversal) to discover research papers. Users start with seed papers and iteratively expand their corpus through citation networks.

**Core Philosophy**: Simple, keyboard-driven workflow for scientists. Fast paper review (Tinder-style), minimal friction, version-control friendly storage.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                        CLI Layer                         │
│                  (src/snowball/cli.py)                   │
└────────────────────┬────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
┌───────▼────────┐       ┌───────▼────────┐
│  TUI (Textual) │       │ Snowball Engine│
│ tui/app.py     │       │ snowballing.py │
└───────┬────────┘       └───────┬────────┘
        │                        │
        │         ┌──────────────┴──────────────┐
        │         │                             │
        │    ┌────▼─────┐              ┌───────▼────────┐
        │    │ Storage  │              │  API Aggregator│
        │    │ JSON     │              │  (4 services)  │
        │    └──────────┘              └────────────────┘
        │
        └────────────────────────────┐
                                     │
                            ┌────────▼────────┐
                            │  PDF Parser     │
                            │ (GROBID/Python) │
                            └─────────────────┘
```

### Key Components

- **Models** (`models.py`): Pydantic models for data validation - Paper, Author, Venue, ReviewProject, FilterCriteria
- **Storage** (`storage/json_storage.py`): Individual JSON files per paper + index. Git-friendly.
- **API Aggregator** (`apis/aggregator.py`): Tries Semantic Scholar → OpenAlex → CrossRef → arXiv with intelligent fallback
- **Snowball Engine** (`snowballing.py`): Core discovery logic, deduplication, filtering
- **TUI** (`tui/app.py`): Textual-based interface with single-column table + expandable details
- **Exporters** (`exporters/`): BibTeX and CSV generation

## Design Decisions

### Why JSON Storage?
Individual files allow Git to track changes per-paper. Scientists can diff, merge, and version control their literature reviews.

### Why Multiple APIs?
Academic APIs have different coverage. Semantic Scholar is best for citations, OpenAlex for metadata, CrossRef for DOIs, arXiv for preprints. Aggregator maximizes discovery.

### Why Textual?
Cross-platform terminal UI with keyboard-first workflow. Scientists live in terminals. Rich rendering without web overhead.

### TUI Layout Evolution
Started with side-by-side panels (list | details), but moved to single-column with expandable details for better space usage. Details limited to 25 lines to prevent scroll issues.

## Coding Conventions

### Style
- PEP 8 compliant
- Type hints everywhere (helps with IDE support)
- Pydantic models for all data structures
- Descriptive variable names over comments

### TUI Patterns

**Color Scheme** (GitHub dark theme):
```python
Background: #0a0e14, #0d1117
Panels: #161b22
Borders: #30363d
Primary: #58a6ff (blue)
Success: #3fb950 (green - included)
Error: #f85149 (red - excluded)
Warning: #d29922 (yellow - pending)
Purple: #a371f7 (maybe)
Text: #c9d1d9
```

**Event Handling**:
- `on_data_table_row_highlighted`: Triggered by arrow keys, shows details automatically
- `on_data_table_row_selected`: Triggered by Enter, toggles details on/off
- Always capture `current_row_index` BEFORE `_refresh_table()`, then use `table.move_cursor(row=next_row)` after refresh

**Sorting Pattern**:
- 3-state cycle per column: ascending → descending → default (Citations desc)
- Return tuple `(priority, value)` from `_get_sort_key()` where priority=0 for valid values, priority=1 for None (sorts to end)
- Clear and re-add columns on sort to update visual indicators (▲/▼)

### Data Flow

**Adding Papers**:
1. Parse PDF or fetch by DOI
2. Enrich with API aggregator
3. Save to `papers/<uuid>.json`
4. Update index in `papers.json`

**Snowballing**:
1. Get included papers from previous iteration
2. Fetch references (backward) and citations (forward)
3. Deduplicate by DOI, then title similarity
4. Apply filters (date, citations, keywords, venue)
5. Save new papers with source and iteration metadata

**Review Cycle**:
1. User navigates with arrow keys (auto-shows details)
2. Quick review: ← exclude, → include (auto-advances to next)
3. Status change → save → refresh table → move cursor to next
4. Press `o` to open DOI/arXiv in browser

## Important Gotchas

### Textual Limitations
- **No clickable links**: Rich's `[link=url]` markup crashes in Static widgets. Use `webbrowser.open()` with keyboard shortcuts instead.
- **Event.label is Rich Text**: Always convert with `str(event.label)` before string operations
- **Widget IDs must be unique**: Don't recreate widgets with same ID in `compose()` - update existing widgets instead

### None Value Handling
Papers may have None for year, citation_count, etc. Always return `(1, 0)` for None in sort keys to push them to the end.

### API Rate Limits
- Semantic Scholar: ~100 requests/5min without key, 5000/5min with key
- OpenAlex & CrossRef: Polite pool with email (2x faster)
- Always respect rate limits, use email parameter

### Table Refresh Pattern
```python
# CORRECT: Preserve cursor position
current_row = table.cursor_row
self._refresh_table()  # Clears table, reloads data
table.move_cursor(row=next_row)  # Restore/advance cursor

# WRONG: Cursor jumps to top
self._refresh_table()
# User loses place in list!
```

## File Structure

```
src/snowball/
├── models.py              # Pydantic models (Paper, Author, etc.)
├── cli.py                 # Click-based CLI commands
├── storage/
│   └── json_storage.py    # JSON persistence layer
├── apis/
│   ├── base.py            # BaseAPIClient abstract class
│   ├── semantic_scholar.py
│   ├── openalex.py
│   ├── crossref.py
│   ├── arxiv.py
│   └── aggregator.py      # Smart fallback aggregator
├── parsers/
│   └── pdf_parser.py      # GROBID + pypdfium2 fallback
├── filters/
│   └── filter_engine.py   # Apply FilterCriteria to papers
├── snowballing.py         # Core discovery engine
├── exporters/
│   ├── bibtex.py          # Generate .bib files
│   └── csv_exporter.py    # Generate CSV/Excel
└── tui/
    └── app.py             # Textual TUI (main interface)
```

## Common Tasks

### Adding a New Status
1. Add to `PaperStatus` enum in `models.py`
2. Add color mapping in `tui/app.py` status_display dict
3. Add keyboard binding in `BINDINGS`
4. Create `action_<status>()` method

### Adding a New API
1. Create `apis/<service>.py` extending `BaseAPIClient`
2. Implement `search_by_doi()`, `search_by_title()`, `get_references()`, `get_citations()`
3. Add to `APIAggregator` fallback chain

### Adding a TUI Column
1. Add column in `on_mount()` and `_refresh_table()`
2. Add sort case in `_get_sort_key()`
3. Add data in `table.add_row()` call

## Future Considerations

**Potential Features**:
- Citation network visualization
- ML-based relevance scoring
- Duplicate detection improvements
- Venue quality database
- PDF annotation import
- Collaborative reviews (multiple users)

**Performance**:
- Current design handles ~1000 papers smoothly
- For >10,000 papers, consider SQLite instead of JSON
- API calls are synchronous - could parallelize with asyncio

## Testing Notes

**Manual Testing Workflow**:
1. `snowball init test-project --min-year 2020`
2. `snowball add-seed test-project --doi "10.1234/example"`
3. `snowball snowball test-project --iterations 1`
4. `snowball review test-project` (test all keyboard shortcuts)
5. `snowball export test-project --format all`

**Edge Cases to Test**:
- Papers with no DOI or arXiv ID
- Papers with >100 authors
- Very long titles (160+ chars)
- Missing abstracts
- None values in sortable columns
- Empty review projects

## Getting Help

- Textual docs: https://textual.textualize.io/
- Semantic Scholar API: https://api.semanticscholar.org/api-docs/
- OpenAlex docs: https://docs.openalex.org/
- GROBID: https://grobid.readthedocs.io/
