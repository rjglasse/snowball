# Using Snowball as a Python Library

This guide shows how to use Snowball programmatically as a Python library, separate from the CLI/TUI interfaces.

## Installation

Install Snowball as a Python package:

```bash
pip install snowball-slr
# or for development
pip install -e .
```

## Quick Start

### 1. Initialize a Review Project

```python
from pathlib import Path
from snowball import (
    ReviewProject,
    FilterCriteria,
    JSONStorage,
)

# Create a project directory
project_dir = Path("my-slr-project")
project_dir.mkdir(exist_ok=True)

# Create project with filter criteria
project = ReviewProject(
    name="Machine Learning in Healthcare",
    description="SLR on ML applications in medical diagnosis",
    research_question="How is machine learning used for medical diagnosis?",
    filter_criteria=FilterCriteria(
        min_year=2015,
        max_year=2024,
        min_citations=5,
        keywords=["machine learning", "diagnosis"],
    ),
)

# Initialize storage and save project
storage = JSONStorage(project_dir)
storage.save_project(project)
```

### 2. Add Seed Papers

```python
from snowball import SnowballEngine, APIAggregator, PDFParser

# Initialize API and engine
api = APIAggregator(
    s2_api_key="your-semantic-scholar-key",  # Optional but recommended
    email="your.email@domain.com",  # For polite API access
)
pdf_parser = PDFParser(use_grobid=True)  # Requires GROBID service
engine = SnowballEngine(storage, api, pdf_parser)

# Add seed from DOI
paper = engine.add_seed_from_doi("10.1234/example.doi", project)
if paper:
    print(f"Added seed: {paper.title}")

# Add seed from PDF
from pathlib import Path
pdf_path = Path("paper.pdf")
paper = engine.add_seed_from_pdf(pdf_path, project)
if paper:
    print(f"Added seed: {paper.title}")
```

### 3. Run Snowballing

```python
# Run one iteration of snowballing
stats = engine.run_snowball_iteration(project, direction="both")

print(f"Discovered: {stats['added']} papers")
print(f"Backward: {stats['backward']} papers")
print(f"Forward: {stats['forward']} papers")
print(f"Auto-excluded: {stats['auto_excluded']} papers")
print(f"For review: {stats['for_review']} papers")

# Reload project to get updated state
project = storage.load_project()
```

### 4. Review Papers

```python
from snowball import PaperStatus

# Get papers pending review
pending_papers = storage.get_papers_by_status(PaperStatus.PENDING)
print(f"Papers to review: {len(pending_papers)}")

# Review papers programmatically
for paper in pending_papers:
    print(f"\nTitle: {paper.title}")
    print(f"Year: {paper.year}")
    print(f"Citations: {paper.citation_count}")
    print(f"Abstract: {paper.abstract[:200]}...")
    
    # Make a decision (in real code, use your logic here)
    decision = "included"  # or "excluded"
    
    # Update paper status
    engine.update_paper_review(
        paper_id=paper.id,
        status=PaperStatus.INCLUDED if decision == "included" else PaperStatus.EXCLUDED,
        notes="Relevant to research question",
        project=project,
    )
```

### 5. Export Results

```python
from snowball import BibTeXExporter, CSVExporter, TikZExporter

# Get all papers
all_papers = storage.load_all_papers()

# Export to BibTeX (only included papers)
bibtex_exporter = BibTeXExporter()
bibtex_content = bibtex_exporter.export(all_papers, only_included=True)
with open("references.bib", "w") as f:
    f.write(bibtex_content)

# Export to CSV (all papers with metadata)
csv_exporter = CSVExporter()
csv_content = csv_exporter.export(all_papers, only_included=False)
with open("papers.csv", "w") as f:
    f.write(csv_content)

# Export citation graph as TikZ
tikz_exporter = TikZExporter()
tikz_content = tikz_exporter.export(
    all_papers,
    only_included=True,
    standalone=True,  # Creates complete LaTeX document
)
with open("citation_graph.tex", "w") as f:
    f.write(tikz_content)
```

## Advanced Usage

### Custom Filtering

```python
from snowball import FilterEngine, FilterCriteria, filter_papers

# Create custom filter criteria
criteria = FilterCriteria(
    min_year=2020,
    max_year=2024,
    min_citations=10,
    keywords=["neural network", "deep learning"],
    excluded_keywords=["review", "survey"],
    venue_types=["journal", "conference"],
)

# Apply filters to papers
filter_engine = FilterEngine()
filtered_papers = filter_engine.apply_filters(all_papers, criteria)
print(f"Filtered to {len(filtered_papers)} papers")

# Or use utility function for simple filtering
from snowball import filter_papers, sort_papers

# Filter by status
included_papers = filter_papers(all_papers, status="included")

# Filter by iteration
iteration_2_papers = filter_papers(all_papers, iteration=2)

# Sort papers
sorted_papers = sort_papers(included_papers, by="citations", ascending=False)
```

### Relevance Scoring

```python
from snowball import TFIDFScorer

# Score papers by relevance to research question
scorer = TFIDFScorer()
research_question = "How is machine learning used for medical diagnosis?"

scored_papers = scorer.score_papers(
    research_question=research_question,
    papers=pending_papers,
    progress_callback=lambda curr, total: print(f"Scored {curr}/{total}"),
)

# Update papers with scores
for paper, score in scored_papers:
    paper.relevance_score = score
    storage.save_paper(paper)

# Sort by relevance
from snowball import sort_papers
top_papers = sort_papers(pending_papers, by="relevance", ascending=False)[:10]
```

### Working with API Clients

```python
from snowball import SemanticScholarClient, OpenAlexClient

# Use individual API clients
s2_client = SemanticScholarClient(api_key="your-key")
paper = s2_client.search_by_doi("10.1234/example.doi")

# Get citations and references
citations = s2_client.get_citations(paper.semantic_scholar_id)
references = s2_client.get_references(paper.semantic_scholar_id)

# Enrich paper metadata
enriched = s2_client.enrich_metadata(paper)

# Use OpenAlex for additional metadata
oa_client = OpenAlexClient(email="your@email.com")
paper = oa_client.search_by_doi("10.1234/example.doi")
```

### PDF Parsing

```python
from snowball import PDFParser

# Initialize parser
parser = PDFParser(use_grobid=True, grobid_url="http://localhost:8070")

# Parse a PDF
result = parser.parse(Path("paper.pdf"))

print(f"Title: {result.title}")
print(f"Authors: {', '.join(result.authors)}")
print(f"Year: {result.year}")
print(f"DOI: {result.doi}")
print(f"References: {len(result.references)}")
print(f"Abstract: {result.abstract[:200]}...")
```

### Visualization

```python
from snowball import generate_citation_graph

# Generate citation network visualization
output_dir = Path("output")
output_dir.mkdir(exist_ok=True)

graph_path = generate_citation_graph(
    papers=all_papers,
    output_dir=output_dir,
    title="Citation Network",
    included_only=True,
)

if graph_path:
    print(f"Graph saved to: {graph_path}")
```

## Data Models

### Paper

```python
from snowball import Paper, PaperStatus, PaperSource, Author, Venue

paper = Paper(
    id="unique-id",
    title="Paper Title",
    authors=[Author(name="John Doe", affiliations=["University"])],
    year=2023,
    abstract="Paper abstract...",
    doi="10.1234/example",
    venue=Venue(name="Conference Name", type="conference"),
    citation_count=42,
    status=PaperStatus.PENDING,
    source=PaperSource.BACKWARD,
    snowball_iteration=1,
)
```

### Project

```python
from snowball import ReviewProject, FilterCriteria

project = ReviewProject(
    name="My Review",
    description="Description of the review",
    research_question="What is the research question?",
    filter_criteria=FilterCriteria(
        min_year=2015,
        max_year=2024,
        min_citations=5,
    ),
)
```

## Integration Examples

### Custom Workflow

```python
from pathlib import Path
from snowball import (
    SnowballEngine,
    JSONStorage,
    APIAggregator,
    ReviewProject,
    FilterCriteria,
    PaperStatus,
)

def run_automated_slr(
    project_dir: Path,
    seed_dois: list[str],
    iterations: int = 2,
):
    """Run an automated SLR workflow."""
    # Setup
    storage = JSONStorage(project_dir)
    api = APIAggregator()
    engine = SnowballEngine(storage, api)
    
    # Create project
    project = ReviewProject(
        name="Automated SLR",
        filter_criteria=FilterCriteria(min_year=2020),
    )
    storage.save_project(project)
    
    # Add seeds
    for doi in seed_dois:
        paper = engine.add_seed_from_doi(doi, project)
        if paper:
            print(f"Added seed: {paper.title}")
    
    # Run iterations
    for i in range(iterations):
        if not engine.should_continue_snowballing(project):
            break
            
        stats = engine.run_snowball_iteration(project, direction="both")
        print(f"Iteration {i+1}: Found {stats['added']} papers")
        
        # Reload project
        project = storage.load_project()
    
    # Get statistics
    stats = storage.get_statistics()
    print(f"\nFinal statistics:")
    print(f"Total papers: {stats['total']}")
    print(f"By status: {stats['by_status']}")
    
    return storage

# Run the workflow
storage = run_automated_slr(
    project_dir=Path("my-project"),
    seed_dois=["10.1234/doi1", "10.5678/doi2"],
    iterations=2,
)
```

### Integration with Web Framework

```python
from flask import Flask, jsonify, request
from snowball import JSONStorage, SnowballEngine, APIAggregator
from pathlib import Path

app = Flask(__name__)
storage = JSONStorage(Path("project"))
api = APIAggregator()
engine = SnowballEngine(storage, api)

@app.route("/api/papers", methods=["GET"])
def get_papers():
    """Get all papers."""
    papers = storage.load_all_papers()
    return jsonify([p.model_dump() for p in papers])

@app.route("/api/papers/<paper_id>/review", methods=["POST"])
def review_paper(paper_id):
    """Update paper review status."""
    data = request.json
    engine.update_paper_review(
        paper_id=paper_id,
        status=data["status"],
        notes=data.get("notes", ""),
    )
    return jsonify({"success": True})

@app.route("/api/snowball", methods=["POST"])
def run_snowball():
    """Run a snowball iteration."""
    project = storage.load_project()
    stats = engine.run_snowball_iteration(project, direction="both")
    return jsonify(stats)

if __name__ == "__main__":
    app.run(debug=True)
```

## API Reference

For detailed API documentation, see:
- Module docstrings: `help(snowball)`
- Class documentation: `help(snowball.SnowballEngine)`
- Function signatures with type hints in the source code

## Best Practices

1. **Always use JSONStorage** for persistence - it's version-control friendly
2. **Provide API credentials** for better rate limits and performance
3. **Use GROBID** for PDF parsing when possible for better accuracy
4. **Apply filters early** to reduce the number of papers to review
5. **Save frequently** - call `storage.save_paper()` after modifications
6. **Handle errors gracefully** - API calls and PDF parsing can fail

## Error Handling

```python
from snowball import APIClientError, RateLimitError

try:
    paper = engine.add_seed_from_doi("10.1234/example", project)
except RateLimitError:
    print("Rate limit exceeded, wait and retry")
except APIClientError as e:
    print(f"API error: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Next Steps

- Explore the CLI documentation for command-line usage
- Check out the TUI for interactive review workflows
- Contribute to the project on GitHub
