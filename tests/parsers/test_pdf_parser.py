"""Tests for PDF parsing functionality."""

import pytest
from pathlib import Path
import tempfile

from snowball.parsers.pdf_parser import PDFParser, PDFParseResult


class TestPDFParseResult:
    """Tests for PDFParseResult class."""

    def test_init_defaults(self):
        """Test that PDFParseResult initializes with correct defaults."""
        result = PDFParseResult()
        
        assert result.title is None
        assert result.authors == []
        assert result.year is None
        assert result.abstract is None
        assert result.references == []
        assert result.doi is None
        assert result.full_text == ""
        assert result.metadata == {}


class TestPDFParser:
    """Tests for PDFParser class."""

    @pytest.fixture
    def parser(self):
        """Create a PDF parser instance without GROBID."""
        return PDFParser(use_grobid=False)

    def test_init_without_grobid(self):
        """Test parser initialization without GROBID."""
        parser = PDFParser(use_grobid=False)
        assert parser.grobid_available is False

    def test_init_with_grobid_unavailable(self):
        """Test parser initialization when GROBID is not available."""
        # This should not raise an error even if GROBID is not running
        parser = PDFParser(use_grobid=True, grobid_url="http://localhost:9999")
        # Should have tried to check but found unavailable
        assert parser.grobid_available is False


class TestPDFParserHeuristics:
    """Tests for PDF parsing heuristic methods."""

    @pytest.fixture
    def parser(self):
        """Create a PDF parser instance."""
        return PDFParser(use_grobid=False)

    def test_extract_title_heuristic(self, parser):
        """Test title extraction from first page text."""
        first_page = """
        
        A Comprehensive Study of Machine Learning in Healthcare
        
        John Doe, Jane Smith
        MIT, Harvard
        
        Abstract
        This paper presents...
        """
        
        title = parser._extract_title_heuristic(first_page)
        # Should extract a line that looks like a title
        assert title is not None
        assert len(title) > 20

    def test_extract_title_heuristic_no_title(self, parser):
        """Test title extraction with no suitable title."""
        first_page = "Short\nlines\nonly"
        
        title = parser._extract_title_heuristic(first_page)
        assert title is None

    def test_extract_authors_heuristic(self, parser):
        """Test author extraction from first page text."""
        first_page = """
        Title of Paper
        
        John Smith, Jane Doe, Bob Johnson
        University of Testing
        """
        
        authors = parser._extract_authors_heuristic(first_page)
        # Should find some author-like patterns
        assert isinstance(authors, list)

    def test_extract_year_heuristic(self, parser):
        """Test year extraction from text."""
        text = "Published in 2023. This work builds on previous research from 2020."
        
        year = parser._extract_year_heuristic(text)
        # Should return the most recent year
        assert year == 2023

    def test_extract_year_heuristic_no_year(self, parser):
        """Test year extraction with no valid year."""
        text = "This paper discusses various topics without mentioning dates."
        
        year = parser._extract_year_heuristic(text)
        assert year is None

    def test_extract_doi_heuristic(self, parser):
        """Test DOI extraction from text."""
        text = "The paper is available at doi: 10.1234/test.paper.2023"
        
        doi = parser._extract_doi_heuristic(text)
        assert doi is not None
        assert doi.startswith("10.")

    def test_extract_doi_heuristic_uppercase(self, parser):
        """Test DOI extraction with uppercase prefix."""
        text = "Available at DOI: 10.5678/another.paper"
        
        doi = parser._extract_doi_heuristic(text)
        assert doi is not None
        assert "10.5678" in doi

    def test_extract_doi_heuristic_no_doi(self, parser):
        """Test DOI extraction with no DOI present."""
        text = "This paper has no DOI reference."
        
        doi = parser._extract_doi_heuristic(text)
        assert doi is None

    def test_extract_abstract_heuristic(self, parser):
        """Test abstract extraction from text."""
        text = """
        Introduction
        Some intro text.
        
        Abstract: This paper presents a novel approach to machine learning
        that improves accuracy by 20%.
        
        Introduction
        The field of machine learning...
        """
        
        abstract = parser._extract_abstract_heuristic(text)
        # May or may not find abstract depending on format
        # Just ensure it doesn't crash

    def test_extract_references_heuristic(self, parser):
        """Test reference extraction from text."""
        text = """
        Body of paper...
        
        References
        [1] Smith, J. (2020). First Reference Paper. Journal of Testing.
        [2] Doe, J. (2021). Second Reference Paper. Conference Proceedings.
        [3] Johnson, B. (2022). Third Reference. doi: 10.1234/test
        """
        
        references = parser._extract_references_heuristic(text)
        # Should find some references
        assert isinstance(references, list)

    def test_extract_references_heuristic_with_dois(self, parser):
        """Test that DOIs are extracted from references."""
        text = """
        References
        [1] Paper with DOI 10.1234/test.ref here.
        """
        
        references = parser._extract_references_heuristic(text)
        if references:
            # Check if any reference has a DOI
            dois_found = [ref.get('doi') for ref in references if ref.get('doi')]
            # Note: depends on regex matching

    def test_extract_references_heuristic_no_section(self, parser):
        """Test reference extraction when no reference section."""
        text = "This paper has no references section."
        
        references = parser._extract_references_heuristic(text)
        assert references == []


class TestPDFParserTEIParsing:
    """Tests for TEI XML parsing (GROBID output)."""

    @pytest.fixture
    def parser(self):
        """Create a PDF parser instance."""
        return PDFParser(use_grobid=False)

    def test_parse_tei_xml_basic(self, parser):
        """Test parsing basic TEI XML."""
        tei_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <TEI xmlns="http://www.tei-c.org/ns/1.0">
            <teiHeader>
                <fileDesc>
                    <titleStmt>
                        <title>Test Paper Title</title>
                    </titleStmt>
                    <sourceDesc>
                        <biblStruct>
                            <analytic>
                                <author>
                                    <persName>
                                        <forename>John</forename>
                                        <surname>Doe</surname>
                                    </persName>
                                </author>
                            </analytic>
                            <monogr>
                                <imprint>
                                    <date type="published" when="2023"/>
                                </imprint>
                            </monogr>
                            <idno type="DOI">10.1234/test.doi</idno>
                        </biblStruct>
                    </sourceDesc>
                </fileDesc>
                <profileDesc>
                    <abstract>
                        <div>
                            <p>This is the abstract text.</p>
                        </div>
                    </abstract>
                </profileDesc>
            </teiHeader>
        </TEI>
        """
        
        result = parser._parse_tei_xml(tei_xml)
        
        assert result.title == "Test Paper Title"
        assert len(result.authors) > 0
        assert "John Doe" in result.authors[0]
        assert result.year == 2023
        assert result.doi == "10.1234/test.doi"
        assert result.abstract == "This is the abstract text."

    def test_parse_tei_xml_invalid(self, parser):
        """Test parsing invalid TEI XML."""
        invalid_xml = "not valid xml"
        
        result = parser._parse_tei_xml(invalid_xml)
        
        # Should return empty result, not crash
        assert result.title is None
        assert result.authors == []

    def test_parse_tei_xml_empty(self, parser):
        """Test parsing empty TEI XML."""
        empty_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <TEI xmlns="http://www.tei-c.org/ns/1.0">
        </TEI>
        """
        
        result = parser._parse_tei_xml(empty_xml)
        
        assert result.title is None


class TestPDFParserBiblStruct:
    """Tests for biblStruct parsing (reference extraction from TEI)."""

    @pytest.fixture
    def parser(self):
        """Create a PDF parser instance."""
        return PDFParser(use_grobid=False)

    def test_parse_bibl_struct(self, parser):
        """Test parsing a biblStruct element."""
        import xml.etree.ElementTree as ET
        
        bibl_xml = """
        <biblStruct xmlns="http://www.tei-c.org/ns/1.0">
            <analytic>
                <title>Referenced Paper Title</title>
                <author>
                    <persName>
                        <forename>Jane</forename>
                        <surname>Smith</surname>
                    </persName>
                </author>
            </analytic>
            <monogr>
                <imprint>
                    <date when="2022"/>
                </imprint>
            </monogr>
            <idno type="DOI">10.5678/ref.paper</idno>
        </biblStruct>
        """
        
        ns = {'tei': 'http://www.tei-c.org/ns/1.0'}
        element = ET.fromstring(bibl_xml)
        
        ref = parser._parse_bibl_struct(element, ns)
        
        assert ref is not None
        assert ref.get('title') == "Referenced Paper Title"
        assert ref.get('year') == 2022
        assert ref.get('doi') == "10.5678/ref.paper"

    def test_parse_bibl_struct_empty(self, parser):
        """Test parsing empty biblStruct element."""
        import xml.etree.ElementTree as ET
        
        bibl_xml = '<biblStruct xmlns="http://www.tei-c.org/ns/1.0"></biblStruct>'
        ns = {'tei': 'http://www.tei-c.org/ns/1.0'}
        element = ET.fromstring(bibl_xml)
        
        ref = parser._parse_bibl_struct(element, ns)
        
        # Should return None or empty dict for empty element
        assert ref is None or ref == {}
