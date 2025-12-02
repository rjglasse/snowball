"""CSV export functionality."""

import pandas as pd
from pathlib import Path
from typing import List, Optional
from ..models import Paper, PaperStatus


class CSVExporter:
    """Exports papers to CSV format."""

    def export(
        self,
        papers: List[Paper],
        output_path: Path,
        only_included: bool = False,
        include_all_fields: bool = False
    ) -> None:
        """Export papers to CSV file.

        Args:
            papers: List of papers to export
            output_path: Path to output CSV file
            only_included: Only export included papers
            include_all_fields: Include all metadata fields
        """
        if only_included:
            papers = [p for p in papers if p.status == PaperStatus.INCLUDED]

        # Convert papers to dataframe
        df = self._papers_to_dataframe(papers, include_all_fields)

        # Export to CSV
        df.to_csv(output_path, index=False, encoding='utf-8')

    def _papers_to_dataframe(self, papers: List[Paper], include_all: bool) -> pd.DataFrame:
        """Convert papers to pandas DataFrame."""
        data = []

        for paper in papers:
            row = {
                "Title": paper.title,
                "Authors": self._format_authors(paper),
                "Year": paper.year,
                "Venue": self._format_venue(paper),
                "DOI": paper.doi,
                "Status": paper.status.value if hasattr(paper.status, 'value') else paper.status,
                "Source": paper.source.value if hasattr(paper.source, 'value') else paper.source,
                "Iteration": paper.snowball_iteration,
                "Citations": paper.citation_count,
                "Notes": paper.notes,
            }

            if include_all:
                row.update({
                    "Abstract": paper.abstract,
                    "Influential_Citations": paper.influential_citation_count,
                    "ArXiv_ID": paper.arxiv_id,
                    "Semantic_Scholar_ID": paper.semantic_scholar_id,
                    "OpenAlex_ID": paper.openalex_id,
                    "PMID": paper.pmid,
                    "Tags": ", ".join(paper.tags) if paper.tags else "",
                    "PDF_Path": paper.pdf_path,
                    "Review_Date": paper.review_date,
                })

            data.append(row)

        return pd.DataFrame(data)

    def _format_authors(self, paper: Paper) -> str:
        """Format authors as a string."""
        if not paper.authors:
            return ""
        return "; ".join([author.name for author in paper.authors])

    def _format_venue(self, paper: Paper) -> str:
        """Format venue as a string."""
        if not paper.venue:
            return ""

        parts = []
        if paper.venue.name:
            parts.append(paper.venue.name)
        if paper.venue.year and paper.venue.year != paper.year:
            parts.append(str(paper.venue.year))

        return " ".join(parts)

    def export_summary(
        self,
        papers: List[Paper],
        output_path: Path,
        include_stats: bool = True
    ) -> None:
        """Export a summary view of papers.

        Args:
            papers: List of papers
            output_path: Output path
            include_stats: Include statistics sheet
        """
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # Main papers sheet
            df = self._papers_to_dataframe(papers, include_all=False)
            df.to_excel(writer, sheet_name='Papers', index=False)

            if include_stats:
                # Statistics sheet
                stats_df = self._generate_statistics(papers)
                stats_df.to_excel(writer, sheet_name='Statistics', index=True)

    def _generate_statistics(self, papers: List[Paper]) -> pd.DataFrame:
        """Generate statistics about the papers."""
        stats = {}

        # Count by status
        for status in PaperStatus:
            count = len([p for p in papers if p.status == status])
            stats[f"Papers - {status.value}"] = count

        # Count by source
        stats["Papers - Seed"] = len([p for p in papers if p.snowball_iteration == 0])
        stats["Papers - Backward"] = len([p for p in papers if str(p.source) == "backward"])
        stats["Papers - Forward"] = len([p for p in papers if str(p.source) == "forward"])

        # Year range
        years = [p.year for p in papers if p.year is not None]
        if years:
            stats["Year - Earliest"] = min(years)
            stats["Year - Latest"] = max(years)

        # Citation stats
        citations = [p.citation_count for p in papers if p.citation_count is not None]
        if citations:
            stats["Citations - Mean"] = sum(citations) / len(citations)
            stats["Citations - Max"] = max(citations)

        return pd.DataFrame.from_dict(stats, orient='index', columns=['Value'])
