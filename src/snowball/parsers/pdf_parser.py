"""PDF parsing with GROBID and fallback support."""

import re
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
import pypdfium2 as pdfium

logger = logging.getLogger(__name__)


class PDFParseResult:
    """Result of PDF parsing."""

    def __init__(self):
        self.title: Optional[str] = None
        self.authors: List[str] = []
        self.year: Optional[int] = None
        self.abstract: Optional[str] = None
        self.references: List[Dict[str, Any]] = []
        self.doi: Optional[str] = None
        self.full_text: str = ""
        self.metadata: Dict[str, Any] = {}


class PDFParser:
    """Parses academic PDFs to extract metadata and references."""

    def __init__(self, use_grobid: bool = True, grobid_url: str = "http://localhost:8070"):
        """Initialize the PDF parser.

        Args:
            use_grobid: Whether to attempt using GROBID
            grobid_url: URL of GROBID service
        """
        self.use_grobid = use_grobid
        self.grobid_url = grobid_url
        self.grobid_available = False

        if use_grobid:
            self.grobid_available = self._check_grobid_available()

    def _check_grobid_available(self) -> bool:
        """Check if GROBID service is available."""
        try:
            import httpx
            response = httpx.get(f"{self.grobid_url}/api/isalive", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.info(f"GROBID not available: {e}")
            return False

    def parse(self, pdf_path: Path) -> PDFParseResult:
        """Parse a PDF file.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            PDFParseResult with extracted information
        """
        if self.grobid_available:
            logger.info(f"Parsing {pdf_path} with GROBID")
            try:
                return self._parse_with_grobid(pdf_path)
            except Exception as e:
                logger.warning(f"GROBID parsing failed: {e}, falling back to Python parser")

        logger.info(f"Parsing {pdf_path} with Python parser")
        return self._parse_with_python(pdf_path)

    def _parse_with_grobid(self, pdf_path: Path) -> PDFParseResult:
        """Parse PDF using GROBID service."""
        try:
            from grobid_client.grobid_client import GrobidClient
        except ImportError:
            logger.warning("grobid-client-python not installed, falling back")
            return self._parse_with_python(pdf_path)

        result = PDFParseResult()

        # Initialize GROBID client
        client = GrobidClient(grobid_server=self.grobid_url)

        # Process the PDF
        import tempfile
        import httpx

        with open(pdf_path, 'rb') as pdf_file:
            files = {'input': pdf_file}
            response = httpx.post(
                f"{self.grobid_url}/api/processFulltextDocument",
                files=files,
                timeout=60
            )

        if response.status_code == 200:
            # Parse TEI XML response
            tei_xml = response.text
            result = self._parse_tei_xml(tei_xml)

        return result

    def _clean_text(self, text: str) -> str:
        """Clean text of Unicode artifacts from PDF extraction.

        Removes problematic characters like \ufffe, \uffff, and other
        replacement/special characters that GROBID sometimes produces.
        """
        if not text:
            return text
        # Remove Unicode replacement and special characters
        # \ufffe and \uffff are "not a character" code points
        # \ufffd is the replacement character
        text = re.sub(r'[\ufffe\uffff\ufffd]', '', text)
        # Collapse multiple spaces that might result from removal
        text = re.sub(r' +', ' ', text)
        return text.strip()

    def _get_element_text(self, elem) -> str:
        """Get all text content from an element, including child elements.

        This handles cases like titles with subtitles in child elements:
        <title>Main Title<title type="sub">: Subtitle</title></title>
        """
        if elem is None:
            return ""
        text = ''.join(elem.itertext()).strip()
        return self._clean_text(text)

    def _parse_tei_xml(self, tei_xml: str) -> PDFParseResult:
        """Parse GROBID's TEI XML output."""
        import xml.etree.ElementTree as ET

        result = PDFParseResult()
        try:
            root = ET.fromstring(tei_xml)
            ns = {'tei': 'http://www.tei-c.org/ns/1.0'}

            # Extract title (including any subtitles in child elements)
            title_elem = root.find('.//tei:titleStmt/tei:title', ns)
            title_text = self._get_element_text(title_elem)
            if title_text:
                result.title = title_text

            # Extract authors
            for author in root.findall('.//tei:sourceDesc//tei:author', ns):
                persName = author.find('.//tei:persName', ns)
                if persName is not None:
                    forename = persName.find('.//tei:forename', ns)
                    surname = persName.find('.//tei:surname', ns)
                    if forename is not None and surname is not None:
                        name = f"{forename.text} {surname.text}".strip()
                        result.authors.append(self._clean_text(name))

            # Extract year
            date_elem = root.find('.//tei:sourceDesc//tei:date[@type="published"]', ns)
            if date_elem is not None and date_elem.get('when'):
                year_str = date_elem.get('when')
                year_match = re.search(r'\d{4}', year_str)
                if year_match:
                    result.year = int(year_match.group())

            # Extract abstract
            abstract_elem = root.find('.//tei:abstract/tei:div/tei:p', ns)
            if abstract_elem is not None and abstract_elem.text:
                result.abstract = abstract_elem.text.strip()

            # Extract DOI
            idno_elem = root.find('.//tei:sourceDesc//tei:idno[@type="DOI"]', ns)
            if idno_elem is not None and idno_elem.text:
                result.doi = idno_elem.text.strip()

            # Extract references
            for biblStruct in root.findall('.//tei:listBibl/tei:biblStruct', ns):
                ref = self._parse_bibl_struct(biblStruct, ns)
                if ref:
                    result.references.append(ref)

        except Exception as e:
            logger.error(f"Error parsing TEI XML: {e}")

        return result

    def _parse_bibl_struct(self, biblStruct, ns) -> Optional[Dict[str, Any]]:
        """Parse a biblStruct element from TEI XML."""
        ref = {}

        # Title (including any subtitles in child elements)
        title_elem = biblStruct.find('.//tei:title', ns)
        title_text = self._get_element_text(title_elem)
        if title_text:
            ref['title'] = title_text

        # Authors
        authors = []
        for author in biblStruct.findall('.//tei:author', ns):
            persName = author.find('.//tei:persName', ns)
            if persName is not None:
                forename = persName.find('.//tei:forename', ns)
                surname = persName.find('.//tei:surname', ns)
                if surname is not None:
                    name_parts = []
                    if forename is not None and forename.text:
                        name_parts.append(forename.text.strip())
                    if surname.text:
                        name_parts.append(surname.text.strip())
                    if name_parts:
                        authors.append(self._clean_text(' '.join(name_parts)))
        if authors:
            ref['authors'] = authors

        # Year
        date_elem = biblStruct.find('.//tei:date', ns)
        if date_elem is not None and date_elem.get('when'):
            year_str = date_elem.get('when')
            year_match = re.search(r'\d{4}', year_str)
            if year_match:
                ref['year'] = int(year_match.group())

        # DOI
        doi_elem = biblStruct.find('.//tei:idno[@type="DOI"]', ns)
        if doi_elem is not None and doi_elem.text:
            ref['doi'] = doi_elem.text.strip()

        return ref if ref else None

    def _parse_with_python(self, pdf_path: Path) -> PDFParseResult:
        """Parse PDF using Python libraries (fallback)."""
        result = PDFParseResult()

        try:
            pdf = pdfium.PdfDocument(str(pdf_path))

            # Extract text from all pages
            full_text = []
            for page_num in range(len(pdf)):
                page = pdf[page_num]
                textpage = page.get_textpage()
                text = textpage.get_text_range()
                full_text.append(text)

            result.full_text = '\n'.join(full_text)

            # Try to extract metadata using heuristics
            first_page = full_text[0] if full_text else ""

            # Extract title (usually the first large text)
            title = self._extract_title_heuristic(first_page)
            if title:
                result.title = title

            # Extract authors
            authors = self._extract_authors_heuristic(first_page)
            result.authors = authors

            # Extract year
            year = self._extract_year_heuristic(first_page)
            if year:
                result.year = year

            # Extract DOI
            doi = self._extract_doi_heuristic(result.full_text)
            if doi:
                result.doi = doi

            # Extract abstract
            abstract = self._extract_abstract_heuristic(result.full_text)
            if abstract:
                result.abstract = abstract

            # Extract references
            references = self._extract_references_heuristic(result.full_text)
            result.references = references

        except Exception as e:
            logger.error(f"Error parsing PDF with Python: {e}")

        return result

    def _extract_title_heuristic(self, first_page: str) -> Optional[str]:
        """Extract title using heuristics."""
        lines = [l.strip() for l in first_page.split('\n') if l.strip()]
        # Title is often one of the first few lines and is capitalized
        for line in lines[:10]:
            if len(line) > 20 and len(line) < 200:
                # Check if it looks like a title (has capital letters, not all caps)
                if line[0].isupper() and not line.isupper():
                    return line
        return None

    def _extract_authors_heuristic(self, first_page: str) -> List[str]:
        """Extract authors using heuristics."""
        # Look for common author patterns
        # This is very basic and may need improvement
        author_pattern = r'([A-Z][a-z]+\s+[A-Z][a-z]+)'
        matches = re.findall(author_pattern, first_page[:1000])
        return matches[:10]  # Limit to reasonable number

    def _extract_year_heuristic(self, text: str) -> Optional[int]:
        """Extract publication year."""
        # Look for 4-digit years in a reasonable range
        year_pattern = r'\b(19\d{2}|20\d{2})\b'
        matches = re.findall(year_pattern, text[:2000])
        if matches:
            # Return the most recent year found (likely publication date)
            years = [int(y) for y in matches]
            return max(years)
        return None

    def _extract_doi_heuristic(self, text: str) -> Optional[str]:
        """Extract DOI."""
        doi_pattern = r'(?:doi|DOI):\s*(10\.\d{4,}/[^\s]+)'
        match = re.search(doi_pattern, text)
        if match:
            return match.group(1).rstrip('.,;')
        return None

    def _extract_abstract_heuristic(self, text: str) -> Optional[str]:
        """Extract abstract."""
        # Look for abstract section
        abstract_pattern = r'(?:Abstract|ABSTRACT)[:\s]+(.*?)(?:\n\n|\n[A-Z][a-z]+:)'
        match = re.search(abstract_pattern, text, re.DOTALL)
        if match:
            abstract = match.group(1).strip()
            # Clean up
            abstract = re.sub(r'\s+', ' ', abstract)
            return abstract[:1000]  # Limit length
        return None

    def _extract_references_heuristic(self, text: str) -> List[Dict[str, Any]]:
        """Extract references using heuristics."""
        references = []

        # Find references section
        ref_section_match = re.search(
            r'(?:References|REFERENCES|Bibliography|BIBLIOGRAPHY)\s+(.*)',
            text,
            re.DOTALL
        )

        if ref_section_match:
            ref_text = ref_section_match.group(1)

            # Split into individual references (numbered)
            ref_pattern = r'\[(\d+)\]\s*(.*?)(?=\[\d+\]|\Z)'
            matches = re.findall(ref_pattern, ref_text, re.DOTALL)

            for num, ref_content in matches[:100]:  # Limit to 100 refs
                ref_content = re.sub(r'\s+', ' ', ref_content).strip()

                # Try to extract title, authors, year, DOI
                ref = {}

                # Extract DOI if present
                doi_match = re.search(r'10\.\d{4,}/[^\s,]+', ref_content)
                if doi_match:
                    ref['doi'] = doi_match.group(0).rstrip('.,;')

                # Extract year
                year_match = re.search(r'\b(19\d{2}|20\d{2})\b', ref_content)
                if year_match:
                    ref['year'] = int(year_match.group(1))

                # Store raw reference text (cleaned)
                ref['raw'] = self._clean_text(ref_content[:500])

                if ref:
                    references.append(ref)

        return references
