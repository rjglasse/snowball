# Snowball Cheatsheet

Quick reference for CLI commands and TUI keyboard shortcuts.

## CLI Commands

### Project Setup

```bash
# Initialize a new project
snowball init <project-dir> [options]
  --name "Project Name"
  --description "Description"
  --min-year 2020
  --max-year 2024
  --research-question "Your RQ here"

# Add seed papers
snowball add-seed <project-dir> --pdf paper1.pdf paper2.pdf
snowball add-seed <project-dir> --doi "10.1234/example"
```

### Snowballing

```bash
# Run snowball iterations
snowball snowball <project-dir> [options]
  --iterations 2              # Limit iterations
  --direction backward        # References only
  --direction forward         # Citations only
  --direction both            # Both (default)
  --force                     # Bypass pending paper check
```

### Review & Export

```bash
# Launch interactive TUI
snowball review <project-dir>

# Export results
snowball export <project-dir> [options]
  --format bibtex|csv|tikz|png|all
  --included-only
  --standalone                # For TikZ: creates compilable .tex
```

### Metadata & Scoring

```bash
# Update citation counts from Google Scholar
snowball update-citations <project-dir>
  --status pending|included|excluded
  --delay 5                   # Seconds between requests

# Set research question
snowball set-rq <project-dir> "Your research question"

# Compute relevance scores
snowball compute-relevance <project-dir>
  --method tfidf|llm
  --model gpt-4o-mini         # For LLM method
  --status pending            # Filter by status

# Parse PDFs and match to papers
snowball parse-pdfs <project-dir>
```

### Scripting & Automation

```bash
# List papers
snowball list <project-dir>
  --status pending|included|excluded
  --iteration 1
  --source seed|backward|forward
  --sort citations|year|title|status
  --format table|json

# Show paper details
snowball show <project-dir>
  --id <paper-uuid>
  --doi "10.1234/example"
  --title "Partial title match"
  --format text|json

# Set paper status
snowball set-status <project-dir>
  --id <paper-uuid>  OR  --doi "10.1234/example"
  --status pending|included|excluded
  --notes "Review notes"

# Project statistics
snowball stats <project-dir>
  --format text|json
```

---

## TUI Keyboard Shortcuts

### Navigation

| Key | Action |
|-----|--------|
| `↑` / `↓` | Move between papers |
| `Enter` / `Space` | Toggle detail view |
| `d` | Toggle details panel visibility |
| Click header | Sort column (asc → desc → default) |

### Quick Review (Tinder-style)

| Key | Action |
|-----|--------|
| `→` or `i` | Include paper (advances to next) |
| `←` | Exclude paper (advances to next) |

### Review Actions

| Key | Action |
|-----|--------|
| `n` | Add/edit notes |
| `u` | Undo last status change |

### Paper Actions

| Key | Action |
|-----|--------|
| `o` | Open DOI/arXiv in browser (or search Scholar) |
| `p` | Open linked PDF locally |
| `l` | Link/unlink PDF to paper |
| `e` | Enrich metadata from APIs |

### Project Actions

| Key | Action |
|-----|--------|
| `s` | Run snowball iteration |
| `x` | Export (BibTeX, CSV, TikZ, PNG) |
| `f` | Cycle filter: All → Pending → Included → Excluded |
| `g` | Generate citation network graph |
| `P` | Parse PDFs in pdfs/inbox/ (Shift+P) |
| `R` | Compute relevance scores (Shift+R) |

### Other

| Key | Action |
|-----|--------|
| `?` | Show help |
| `q` | Quit |

---

## Environment Variables

```bash
# Add to ~/.bashrc or ~/.zshrc
export SEMANTIC_SCHOLAR_API_KEY="your-key"
export SNOWBALL_EMAIL="your@email.com"
export OPENAI_API_KEY="sk-..."  # For LLM relevance scoring
```

---

## Typical Workflow

```bash
# 1. Initialize project
snowball init my-slr --name "My Review" --min-year 2020 \
  --research-question "What are the benefits of X?"

# 2. Add seed papers
snowball add-seed my-slr --doi "10.1234/seed1" "10.1234/seed2"

# 3. Review seeds in TUI (ensure they're included)
snowball review my-slr
# → Use i/→ to include, ←to exclude

# 4. Run snowballing
snowball snowball my-slr --iterations 1

# 5. Review discovered papers
snowball review my-slr
# → Press R to compute relevance scores
# → Sort by Rel column to prioritize high-relevance papers
# → Use i/→/← for quick review

# 6. Repeat steps 4-5 until no pending papers remain

# 7. Export final results
snowball export my-slr --format all --included-only
```

---

## Column Legend (TUI)

| Column | Description |
|--------|-------------|
| Status | ✓ Included / ✗ Excluded / ? Pending |
| Title | Paper title (truncated) |
| Year | Publication year (red if outside filter range) |
| Rel | Relevance score (0.00-1.00, green=high) |
| Refs | GROBID-extracted reference count |
| Cite | Citation count from APIs |
| Obs | Observation count (times discovered) |
| Source | Seed / Bkd (backward) / Fwd (forward) |
| Iter | Snowball iteration number |
| PDF | Indicator if PDF is linked |
