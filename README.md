# Snowball SLR

A terminal-based tool for conducting Systematic Literature Reviews (SLR) using the snowballing methodology.

## Features

- **Seed Paper Import**: Start from PDF files or DOIs
- **Bidirectional Snowballing**: Discover papers through both backward (references) and forward (citations) snowballing
- **Multiple API Integration**:
  - Semantic Scholar (primary source for citations)
  - OpenAlex (comprehensive scholarly data)
  - CrossRef (DOI-based metadata)
  - arXiv (preprints)
- **Intelligent Filtering**: Auto-filter papers by date range, citation count, keywords, and venue quality
- **Interactive TUI**: Rich terminal interface for reviewing papers
- **PDF Parsing**: Extract metadata from PDFs using GROBID or Python fallback
- **Export**: Generate BibTeX bibliographies and CSV spreadsheets
- **JSON Storage**: Human-readable project files for easy version control

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

## Quick Start

### 1. Initialize a Project

```bash
snowball init my-slr-project \
  --name "Machine Learning in Healthcare" \
  --description "SLR on ML applications in medical diagnosis" \
  --max-iterations 2 \
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

The TUI features a clean, GitHub-inspired dark theme with a sortable table interface:

**Navigation:**
- `↑`/`↓` Arrow keys: Navigate papers (details appear automatically)
- `Enter`: Toggle detail view on/off
- Click column headers: Sort by that column (ascending → descending → default)

**Quick Review (Tinder-style):**
- `→` Right arrow or `i`: Include paper (and advance to next)
- `←` Left arrow or `e`: Exclude paper (and advance to next)

**Review Actions:**
- `m`: Mark as Maybe
- `p`: Mark as Pending
- `n`: Add/edit notes
- `o`: Open paper's DOI or arXiv URL in browser

**Other Controls:**
- `s`: Run another snowball iteration
- `x`: Export results (BibTeX + CSV)
- `q`: Quit

**Features:**
- Auto-advance to next paper after include/exclude
- Sortable columns: Status, Title, Year, Citations, Source, Iteration
- Expandable paper details with abstract, authors, and metadata
- Real-time statistics panel showing included/excluded/pending counts

### 4b. Non-Interactive Review (for AI Agents/Scripts)

Snowball also provides non-interactive CLI commands for automation and AI agents:

```bash
# List papers with filtering options
snowball list my-slr-project --status pending --format json
snowball list my-slr-project --iteration 1 --sort citations

# View paper details
snowball show my-slr-project --id paper-uuid
snowball show my-slr-project --doi "10.1234/example" --format json
snowball show my-slr-project --title "machine learning"

# Set paper status
snowball set-status my-slr-project --id paper-uuid --status included --notes "Relevant"
snowball set-status my-slr-project --doi "10.1234/example" --status excluded

# View project statistics
snowball stats my-slr-project --format json
```

**Available Commands:**
- `list` - List papers with filters (status, iteration, source) and sorting
- `show` - View detailed paper information by ID, DOI, or title
- `set-status` - Update paper status (pending, included, excluded, maybe)
- `stats` - View project statistics

All commands support `--format json` for machine-readable output.

### 5. Export Results

```bash
# Export included papers to BibTeX
snowball export my-slr-project --format bibtex --included-only

# Export all papers to CSV with full metadata
snowball export my-slr-project --format csv

# Export both formats
snowball export my-slr-project --format all
```

## Workflow

```
┌─────────────────┐
│  Seed Papers    │
│  (PDF or DOI)   │
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│  Snowball Iteration 0   │
│  - Extract metadata     │
│  - Enrich with APIs     │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  Snowball Iteration 1   │
│  - Get references       │
│  - Get citations        │
│  - Apply filters        │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  Manual Review          │
│  - Include/Exclude      │
│  - Add notes            │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  Snowball Iteration 2   │
│  - Continue from        │
│    included papers      │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  Export Results         │
│  - BibTeX bibliography  │
│  - CSV spreadsheet      │
└─────────────────────────┘
```

## Configuration

### API Keys (Optional but Recommended)

While most APIs work without keys, you'll get higher rate limits with authentication:

**Semantic Scholar API Key:**
1. Register at https://www.semanticscholar.org/product/api
2. Use with `--s2-api-key` flag

**Email for Polite Pools:**
- CrossRef and OpenAlex offer faster service if you provide an email
- Use with `--email` flag

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

## Project Structure

```
my-slr-project/
├── project.json              # Project metadata and configuration
├── papers.json              # Index of all papers
├── papers/                  # Individual paper JSON files
│   ├── uuid1.json
│   ├── uuid2.json
│   └── ...
├── included_papers.bib      # Exported BibTeX (after export)
└── all_papers.csv          # Exported CSV (after export)
```

## Advanced Usage

### Programmatic API

```python
from pathlib import Path
from snowball.storage.json_storage import JSONStorage
from snowball.apis.aggregator import APIAggregator
from snowball.snowballing import SnowballEngine
from snowball.models import ReviewProject, FilterCriteria

# Set up
storage = JSONStorage(Path("my-project"))
api = APIAggregator(email="your@email.com")
engine = SnowballEngine(storage, api)

# Create project
project = ReviewProject(
    name="My Review",
    max_iterations=2,
    filter_criteria=FilterCriteria(min_year=2020)
)
storage.save_project(project)

# Add seed from DOI
paper = engine.add_seed_from_doi("10.1234/example", project)

# Run snowballing
stats = engine.run_snowball_iteration(project)
print(f"Discovered {stats['added']} papers")

# Review papers
papers = engine.get_papers_for_review()
for paper in papers:
    print(f"Review: {paper.title}")
    # ... make decision ...
    engine.update_paper_review(
        paper.id,
        PaperStatus.INCLUDED,
        "Relevant to my research"
    )
```

### Custom Filters

Modify `filter_criteria` to create sophisticated filters:

```python
from snowball.models import FilterCriteria

criteria = FilterCriteria(
    min_year=2018,
    max_year=2024,
    min_citations=10,
    min_influential_citations=2,
    keywords=["neural network", "transformer"],
    excluded_keywords=["survey", "review"],
    venue_types=["journal", "conference"]
)
```

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

## Contributing

Contributions welcome! Areas for improvement:
- Additional API integrations
- Enhanced PDF parsing
- Better venue quality detection
- Citation network visualization
- Machine learning-based relevance scoring

### Development Setup

For development, we use `uv` for fast dependency management:

```bash
# Install uv
pipx install uv

# Clone and set up the project
git clone <repo-url>
cd snowball

# Install all dependencies including dev tools
uv sync --extra dev

# Run tests
uv run pytest

# Run linters
uv run black .
uv run ruff check .

# Run the tool in development mode
uv run snowball --help
```

The project uses:
- **pytest** for testing
- **black** for code formatting
- **ruff** for linting
- **uv** for dependency management

All dependencies are locked in `uv.lock` for reproducible builds.

## License

MIT License - see LICENSE file

## Citation

If you use Snowball in your research, please cite:

```bibtex
@software{snowball_slr,
  title = {Snowball: A Tool for Systematic Literature Review},
  author = {Your Name},
  year = {2024},
  url = {https://github.com/yourusername/snowball}
}
```

## Acknowledgments

Built with:
- [Textual](https://textual.textualize.io/) - TUI framework
- [Semantic Scholar API](https://www.semanticscholar.org/product/api)
- [OpenAlex](https://openalex.org/)
- [CrossRef](https://www.crossref.org/)
- [arXiv](https://arxiv.org/)
- [GROBID](https://github.com/kermitt2/grobid)
