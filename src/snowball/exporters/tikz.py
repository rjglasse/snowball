"""TikZ/LaTeX export functionality for citation graphs."""

from typing import List, Dict, Tuple
from ..models import Paper, PaperStatus


class TikZExporter:
    """Exports citation graphs to TikZ/LaTeX format."""

    def export(
        self,
        papers: List[Paper],
        only_included: bool = True,
        standalone: bool = False,
    ) -> str:
        """Export papers as a TikZ citation graph.

        Args:
            papers: List of papers to export
            only_included: Only export included papers (default True)
            standalone: Generate standalone LaTeX document (default False)

        Returns:
            TikZ/LaTeX code as a string
        """
        if only_included:
            papers = [p for p in papers if p.status == PaperStatus.INCLUDED]

        if not papers:
            return ""

        # Build paper lookup for edge creation
        paper_lookup = {p.id: p for p in papers}
        paper_ids = set(paper_lookup.keys())

        # Group nodes by iteration
        iterations = {}
        for paper in papers:
            iter_num = paper.snowball_iteration
            if iter_num not in iterations:
                iterations[iter_num] = []
            iterations[iter_num].append(paper)

        # Sort nodes within each iteration by citation count (highest at top)
        for iter_num in iterations:
            iterations[iter_num].sort(key=lambda p: p.citation_count or 0, reverse=True)

        # Calculate positions
        pos = {}
        x_spacing = 10.0  # Horizontal spacing between iterations (in cm)
        y_spacing = 2.5  # Vertical spacing between nodes (in cm)

        for iter_num in sorted(iterations.keys()):
            papers_in_iter = iterations[iter_num]
            x = iter_num * x_spacing

            # Center nodes vertically
            total_height = (len(papers_in_iter) - 1) * y_spacing
            start_y = total_height / 2

            for i, paper in enumerate(papers_in_iter):
                y = start_y - (i * y_spacing)
                pos[paper.id] = (x, y)

        # Collect edges
        edges = []
        for paper in papers:
            for source_id in paper.source_paper_ids:
                if source_id in paper_ids:
                    edges.append((source_id, paper.id))

        # Generate TikZ code
        tikz_code = self._generate_tikz_code(
            papers=papers,
            positions=pos,
            edges=edges,
            paper_lookup=paper_lookup,
        )

        if standalone:
            return self._wrap_standalone(tikz_code)

        return tikz_code

    def _generate_tikz_code(
        self,
        papers: List[Paper],
        positions: Dict[str, Tuple[float, float]],
        edges: List[Tuple[str, str]],
        paper_lookup: Dict[str, Paper],
    ) -> str:
        """Generate the core TikZ code for the citation graph."""
        lines = []

        # TikZ picture environment start
        lines.append(r"\begin{tikzpicture}[")
        lines.append(r"  node distance=2cm,")
        lines.append(r"  paper/.style={")
        lines.append(r"    rectangle,")
        lines.append(r"    draw=none,")
        lines.append(r"    fill=white,")
        lines.append(r"    text width=5cm,")
        lines.append(r"    align=center,")
        lines.append(r"    font=\small,")
        lines.append(r"    inner sep=5pt")
        lines.append(r"  },")
        lines.append(r"  citation/.style={")
        lines.append(r"    ->,")
        lines.append(r"    >=stealth,")
        lines.append(r"    thick,")
        lines.append(r"    color=black!60,")
        lines.append(r"    out=0,")
        lines.append(r"    in=180,")
        lines.append(r"    looseness=1.2")
        lines.append(r"  }")
        lines.append(r"]")
        lines.append("")

        # Add nodes
        for paper in papers:
            if paper.id not in positions:
                continue

            x, y = positions[paper.id]
            node_id = self._sanitize_id(paper.id)
            title = self._escape_latex(self._truncate_title(paper.title))

            # Add author and year info if available
            metadata = []
            if paper.authors and len(paper.authors) > 0:
                author_name = paper.authors[0].name.strip()
                if author_name:
                    first_author = author_name.split()[-1]  # Last name
                    if len(paper.authors) > 1:
                        metadata.append(f"{first_author} et al.")
                    else:
                        metadata.append(first_author)

            if paper.year:
                metadata.append(str(paper.year))

            metadata_str = ", ".join(metadata)
            if metadata_str:
                label_text = f"\\textbf{{{title}}}\\\\[2pt]{{\\footnotesize {self._escape_latex(metadata_str)}}}"
            else:
                label_text = f"\\textbf{{{title}}}"

            lines.append(f"\\node[paper] ({node_id}) at ({x}cm,{y}cm) {{{label_text}}};")

        lines.append("")

        # Add edges (from east anchor to west anchor with S-curves)
        for source_id, target_id in edges:
            source_node = self._sanitize_id(source_id)
            target_node = self._sanitize_id(target_id)
            lines.append(f"\\draw[citation] ({source_node}.east) to ({target_node}.west);")

        lines.append("")
        lines.append(r"\end{tikzpicture}")

        return "\n".join(lines)

    def _wrap_standalone(self, tikz_code: str) -> str:
        """Wrap TikZ code in a standalone LaTeX document."""
        lines = [
            r"\documentclass[tikz,border=10pt]{standalone}",
            r"\usepackage{tikz}",
            r"\usetikzlibrary{arrows.meta,positioning}",
            r"",
            r"\begin{document}",
            "",
            tikz_code,
            "",
            r"\end{document}",
        ]
        return "\n".join(lines)

    def _truncate_title(self, title: str, max_length: int = 60) -> str:
        """Truncate title if too long."""
        if not title:
            return ""
        if len(title) <= max_length:
            return title
        # Truncate and try to break at word boundary
        truncated = title[:max_length]
        parts = truncated.rsplit(" ", 1)
        if len(parts) > 1:
            return parts[0] + "..."
        # No spaces found, just truncate
        return truncated + "..."

    def _escape_latex(self, text: str) -> str:
        """Escape special LaTeX characters."""
        if not text:
            return ""

        replacements = {
            "\\": r"\textbackslash{}",
            "&": r"\&",
            "%": r"\%",
            "$": r"\$",
            "#": r"\#",
            "_": r"\_",
            "{": r"\{",
            "}": r"\}",
            "~": r"\textasciitilde{}",
            "^": r"\textasciicircum{}",
        }

        for char, replacement in replacements.items():
            text = text.replace(char, replacement)

        return text

    def _sanitize_id(self, node_id: str) -> str:
        """Sanitize node ID for use in TikZ."""
        # Replace special characters with underscores
        sanitized = ""
        for char in node_id:
            if char.isalnum() or char in ["-", "_"]:
                sanitized += char
            else:
                sanitized += "_"
        return f"node_{sanitized}"
