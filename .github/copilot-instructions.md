# Copilot Instructions for Snowball SLR

This repository contains **Snowball SLR**, a terminal-based Python tool for conducting Systematic Literature Reviews using the snowballing methodology.

> **Important**: For detailed architecture diagrams, design decisions, gotchas, and TUI patterns, see [`/CLAUDE.md`](/CLAUDE.md).

## Project Overview

- **Purpose**: Automate the discovery and management of academic papers through backward (references) and forward (citations) snowballing
- **Architecture**: CLI application with interactive TUI (Textual framework)
- **Data Storage**: JSON-based storage for projects and papers

## Tech Stack

- **Python 3.9+** with type hints
- **Textual** for the terminal user interface
- **Pydantic** for data models and validation
- **pytest** for testing
- **black** and **ruff** for code formatting and linting

## Code Structure

```
src/snowball/
├── apis/           # API integrations (Semantic Scholar, OpenAlex, CrossRef, arXiv)
├── exporters/      # BibTeX and CSV export functionality
├── filters/        # Paper filtering logic
├── parsers/        # PDF parsing (GROBID and Python fallback)
├── storage/        # JSON-based storage implementation
├── tui/            # Textual TUI components
├── cli.py          # argparse-based CLI entry point
├── models.py       # Pydantic data models
└── snowballing.py  # Core snowballing engine
```

## Coding Conventions

- Use **type hints** for all function signatures
- Follow **PEP 8** style guidelines
- Use **Pydantic models** for data structures
- Prefer **async/await** for API calls
- Keep functions focused and single-purpose
- Write descriptive docstrings for public APIs

## Testing Guidelines

- Write tests using **pytest**
- Create a `tests/` directory mirroring the `src/` structure when adding tests
- Use fixtures for common test data
- Mock external API calls in unit tests

## Common Tasks

### Adding a New API Integration

1. Create a new module in `src/snowball/apis/`
2. Implement the API client following existing patterns
3. Add the integration to the `APIAggregator` in `apis/aggregator.py`
4. Handle rate limiting and error responses gracefully

### Modifying the TUI

1. TUI components are in `src/snowball/tui/`
2. Follow Textual framework conventions
3. Use the existing dark theme styling
4. Test UI changes interactively with `snowball review`

### Adding Export Formats

1. Create a new exporter in `src/snowball/exporters/`
2. Follow the existing exporter interface pattern
3. Add the format option to the CLI export command

## Dependencies

- External API calls should use `httpx` for async support
- PDF parsing prefers GROBID when available, falls back to `pypdfium2`
- Data validation uses Pydantic v2 syntax
