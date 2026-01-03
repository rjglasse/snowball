# Snowball 

A terminal-based tool for conducting Systematic Literature Reviews (SLR) using the snowballing methodology.

**Snowball can be used both as a CLI/TUI application and as a Python library** for programmatic access to snowballing functionality.

<img width="1770" height="757" alt="snowball-tui" src="https://github.com/user-attachments/assets/ce7b42f7-a0dd-480d-853b-b96ef9907087" />

## How it works

- Start by adding seed papers (via PDF or DOI)
- Review seed papers for inclusion (just in case)
- Snowball backwards (via references), forwards (via citations) or both (optionally setting time period)
  - [Grobid](https://github.com/kermitt2/grobid/) is used to extract references
  - APIs like [OpenAlex](https://openalex.org/) and [Semantic Scholar](https://www.semanticscholar.org/) are used to find citations
- Review list of found papers for inclusion or exclusion
  - Simple keyboard shortcut interaction
  - Filter by keyword or review status 
  - Enhance metadata by fetching abstract, citations, etc
  - Open DOI (if available) in web browser for more info and to access PDF
  - Repair any errors in metadata
- Once there are no more "Pending" papers, add PDFs to the project's PDF folder and snowball again.

## Quick Start

### 1. Initialize a Project

```bash
snowball init my-slr-project \
  --name "Machine Learning in Healthcare" \
  --description "SLR on ML applications in medical diagnosis" \
  --min-year 2015 \
  --max-year 2024
```

### 2. Add Seed Papers

From PDF files:
```bash
snowball add-seed my-slr-project \
  --pdf seed1.pdf seed2.pdf \
  --email your.email@domain.com
```

From DOIs:
```bash
snowball add-seed my-slr-project \
  --doi "10.1234/example.doi" "10.5678/another.doi" \
  --s2-api-key YOUR_SEMANTIC_SCHOLAR_KEY \
  --email your.email@domain.com
```

### 3. Run Snowballing

```bash
snowball snowball my-slr-project \
  --iterations 2 \
  --email your.email@domain.com
```

You can also specify which direction to snowball:

```bash
# Only backward snowballing (papers referenced by your seeds)
snowball snowball my-slr-project --direction backward

# Only forward snowballing (papers citing your seeds)
snowball snowball my-slr-project --direction forward

# Both directions (default)
snowball snowball my-slr-project --direction both
```

This will:
- Find all papers referenced by your seeds (backward) - if direction is "backward" or "both"
- Find all papers citing your seeds (forward) - if direction is "forward" or "both"
- Apply your configured filters
- Save all discovered papers for review

### 4. Review Papers

Launch the interactive TUI:
```bash
snowball review my-slr-project
```

**Navigation:**
- `↑`/`↓`: Navigate papers (details appear automatically)
- `Enter`/`Space`: Toggle detail view on/off
- `d`: Toggle details panel visibility
- Click column headers: Sort by that column (ascending → descending → default)

**Quick Review (Tinder-style):**
- `→` or `i`: Include paper (and advance to next)
- `←`: Exclude paper (and advance to next)

**Review Actions:**
- `n`: Add/edit notes
- `u`: Undo last status change

**Paper Actions:**
- `o`: Open paper's DOI, arXiv URL, or search Google Scholar
- `p`: Open local PDF file
- `l`: Link/unlink a PDF to the current paper
- `e`: Enrich metadata from APIs (abstract, citations, etc.)

**Project Actions:**
- `s`: Run another snowball iteration
- `x`: Export results (BibTeX, CSV, TikZ, PNG)
- `f`: Cycle filter (All → Pending → Included → Excluded)
- `g`: Generate citation network graph
- `P`: Parse PDFs in pdfs/inbox/ folder (Shift+P)
- `R`: Compute relevance scores (Shift+R)

**Other:**
- `?`: Show help with all shortcuts
- `q`: Quit

### 5. Export Results

```bash
# Export included papers to BibTeX
snowball export my-slr-project --format bibtex --included-only

# Export all papers to CSV with full metadata
snowball export my-slr-project --format csv

# Export citation graph as TikZ/LaTeX code
snowball export my-slr-project --format tikz --included-only

# Export citation graph as standalone LaTeX document
snowball export my-slr-project --format tikz --included-only --standalone

# Export all formats (BibTeX, CSV, and TikZ)
snowball export my-slr-project --format all
```

**TikZ Export:**
- Generates publication-ready LaTeX/TikZ code for citation network visualization
- Use `--standalone` to create a complete LaTeX document (compile with `pdflatex`)
- Without `--standalone`, generates TikZ code for embedding in your own LaTeX document
- Papers are positioned by iteration (left to right) and sorted by citation count

### 6. Relevance Scoring (Optional)

If you set a research question, Snowball can score papers by relevance to help prioritize review:

```bash
# Set research question during init
snowball init my-slr-project \
  --name "ML in Healthcare" \
  --research-question "How is machine learning used for medical diagnosis?"

# Or set/update research question later
snowball set-rq my-slr-project "How is machine learning used for medical diagnosis?"

# Compute relevance scores for pending papers
snowball compute-relevance my-slr-project --method tfidf   # Fast, offline
snowball compute-relevance my-slr-project --method llm     # Uses OpenAI API (requires OPENAI_API_KEY)
```

Relevance scores (0.0–1.0) appear in the "Rel" column in the TUI. Press `R` in the TUI to compute scores interactively.

### 7. PDF Management

Snowball supports two PDF workflows:

**Automatic matching (inbox):**
```bash
# Place PDFs in pdfs/inbox/ folder
cp paper1.pdf paper2.pdf my-slr-project/pdfs/inbox/

# Parse and auto-match by title
snowball parse-pdfs my-slr-project
# Matched PDFs are moved to pdfs/, unmatched stay in inbox/
```

**Manual linking (TUI):**
- Press `l` to link any PDF from pdfs/ or pdfs/inbox/ to the current paper
- Press `p` to open the linked PDF

### 8. Update Citation Counts (Optional)

Update citation counts from Google Scholar for more accurate/current data:

```bash
# Update all papers
snowball update-citations my-slr-project

# Update only included papers
snowball update-citations my-slr-project --status included

# Custom delay between requests (default: 5 seconds)
snowball update-citations my-slr-project --delay 3
```

**Note:** This uses Google Scholar scraping via the `scholarly` library. Use responsibly with appropriate delays to avoid being rate-limited.

### 9. Non-Interactive Commands (Scripting/AI Agents)

These commands support automation and AI-assisted workflows:

```bash
# List papers with filtering and sorting
snowball list my-slr-project                           # All papers
snowball list my-slr-project --status pending          # Only pending
snowball list my-slr-project --iteration 1 --format json

# Show detailed paper information
snowball show my-slr-project --doi "10.1234/example"
snowball show my-slr-project --title "Machine Learning" --format json

# Update paper status programmatically
snowball set-status my-slr-project --id <paper-id> --status included
snowball set-status my-slr-project --doi "10.1234/example" --status excluded --notes "Out of scope"

# Get project statistics
snowball stats my-slr-project
snowball stats my-slr-project --format json
```

## Configuration

### API Keys (Optional but Recommended)

While most APIs work without keys, you'll get higher rate limits with authentication:

**Semantic Scholar API Key:**
1. Register at https://www.semanticscholar.org/product/api
2. Set via environment variable (recommended) or CLI flag

**Email for Polite Pools:**
- CrossRef and OpenAlex offer faster service if you provide an email
- Set via environment variable (recommended) or CLI flag

**Environment Variables (Recommended):**

Add these to your shell profile (`~/.bashrc`, `~/.zshrc`, etc.):

```bash
export SEMANTIC_SCHOLAR_API_KEY="your-api-key-here"
export SNOWBALL_EMAIL="your.email@domain.com"
```

Then commands will automatically use these credentials:
```bash
snowball snowball my-project  # Uses env vars automatically
```

**CLI Flags (Alternative):**

You can also pass credentials per-command:
```bash
snowball snowball my-project --s2-api-key YOUR_KEY --email your@email.com
```

CLI flags override environment variables when both are set.

### GROBID (Optional)

For best PDF parsing results, install GROBID:

```bash
# Using Docker
docker run -p 8070:8070 lfoppiano/grobid:0.8.0

# Or install manually following https://grobid.readthedocs.io/
```

If GROBID is not available, Snowball will automatically fall back to Python-based PDF parsing.

### Filter Criteria

Configure auto-filtering in the `init` command or edit `project.json`:

```json
{
  "filter_criteria": {
    "min_year": 2015,
    "max_year": 2024,
    "min_citations": 5,
    "keywords": ["machine learning", "deep learning"],
    "excluded_keywords": ["deprecated", "retracted"],
    "venue_types": ["journal", "conference"]
  }
}
```

## Using Snowball as a Python Library

Snowball can be used programmatically as a Python library, allowing you to integrate snowballing into your own workflows, scripts, or applications.

### Quick Example

```python
from pathlib import Path
from snowball import (
    SnowballEngine,
    JSONStorage,
    APIAggregator,
    ReviewProject,
    FilterCriteria,
)

# Initialize components
storage = JSONStorage(Path("my-project"))
api = APIAggregator()
engine = SnowballEngine(storage, api)

# Create project
project = ReviewProject(
    name="My Review",
    filter_criteria=FilterCriteria(min_year=2020),
)
storage.save_project(project)

# Add seed paper
paper = engine.add_seed_from_doi("10.1234/example.doi", project)

# Run snowballing
stats = engine.run_snowball_iteration(project, direction="both")
print(f"Found {stats['added']} papers")

# Get papers for review
from snowball import PaperStatus
pending = storage.get_papers_by_status(PaperStatus.PENDING)

# Export results
from snowball import BibTeXExporter
exporter = BibTeXExporter()
bibtex = exporter.export(storage.load_all_papers(), only_included=True)
```

For comprehensive documentation on using Snowball as a library, see **[API_USAGE.md](API_USAGE.md)**.

### Available Components

The public API includes:
- **Core Engine**: `SnowballEngine` for running iterations
- **Storage**: `JSONStorage` for persistence
- **API Clients**: `APIAggregator`, `SemanticScholarClient`, `OpenAlexClient`, etc.
- **Parsers**: `PDFParser` for extracting metadata from PDFs
- **Exporters**: `BibTeXExporter`, `CSVExporter`, `TikZExporter`
- **Filters**: `FilterEngine` for applying criteria
- **Scoring**: `TFIDFScorer`, `LLMScorer` for relevance scoring
- **Models**: `Paper`, `ReviewProject`, `FilterCriteria`, etc.

## Troubleshooting

### PDF Parsing Issues

If PDF metadata extraction fails:
1. Try with GROBID if not already using it
2. Use DOI instead: `--doi` rather than `--pdf`
3. Check PDF is not scanned/image-based
4. Manually add metadata by editing the paper JSON file

### API Rate Limits

If you hit rate limits:
1. Use API keys (`--s2-api-key`)
2. Provide email for polite pools (`--email`)
3. Add delays between operations
4. Process seeds in smaller batches

### Missing Citations/References

Some papers may not have citation data:
- Very recent papers have fewer citations
- Some venues aren't well-indexed
- Try multiple APIs (aggregator tries all automatically)
- Consider using different seed papers

## Installation

### Using uv (Recommended)

[uv](https://github.com/astral-sh/uv) is a fast Python package installer and resolver. It's the recommended way to work with this project for development:

```bash
# Install uv (if not already installed)
pipx install uv

# Clone the repository
git clone <repo-url>
cd snowball

# Sync dependencies and create virtual environment
uv sync

# Run the tool
uv run snowball --help

# Optional: Install with GROBID support
uv sync --extra grobid

# Optional: Install development dependencies (for testing/linting)
uv sync --extra dev
```

The `uv sync` command will:
- Create a `.venv` virtual environment in the project directory
- Install all dependencies from the lockfile (`uv.lock`)
- Install the `snowball` package in editable mode

You can then run commands with `uv run <command>`, which automatically uses the virtual environment.

### Using pipx (Alternative)

```bash
# Install pipx (if not already installed)
python -m pip install --user pipx
pipx ensurepath
# Note: You may need to restart your terminal or run 'source ~/.bashrc' (Linux/Mac)
# or 'source ~/.bash_profile' (Mac) for PATH changes to take effect

# Install the package from the repository
pipx install git+<repo-url>

# Or install from a local clone
git clone <repo-url>
cd snowball
pipx install .

# Optional: Install with GROBID support
pipx install "git+<repo-url>[grobid]"
# Or from local: pipx install ".[grobid]"

# Note: For development work with editable installs, use uv instead
```

## Citation

If you use Snowball in your research, please cite:

```bibtex
@software{snowball_2005,
  title = {Snowball: A Tool for Systematic Literature Reviews},
  author = {Richard Glassey and Daniel Bosk},
  year = {2025},
  url = {https://github.com/rjglasse/snowball}
}
```

## Acknowledgments

Built with:
- [Textual](https://textual.textualize.io/)
- [Semantic Scholar API](https://www.semanticscholar.org/product/api)
- [OpenAlex](https://openalex.org/)
- [CrossRef](https://www.crossref.org/)
- [arXiv](https://arxiv.org/)
- [GROBID](https://github.com/kermitt2/grobid)
