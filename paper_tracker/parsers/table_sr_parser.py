"""Parser for Super Resolution style markdown tables.

Handles 5-column format: Title | Model | Published | Code | Keywords
Used by: Awesome-Super-Resolution, Awesome-Deblurring, Deraining lists
"""

import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from .base_parser import BaseAwesomeParser, ParserCapabilities
from . import ParserRegistry


@ParserRegistry.register
class TableSRParser(BaseAwesomeParser):
    """Parser for Super Resolution / Deblurring style tables.

    Expected format:
    | Title | Model | Published | Code | Keywords |
    |-------|-------|-----------|------|----------|
    | [Paper Title](url) | ModelName | CVPR'24 | [GitHub](url) | tag1, tag2 |
    """

    name = "table_sr"
    version = "1.0.0"

    # Pattern to detect table headers
    TABLE_HEADER_PATTERN = re.compile(
        r'\|\s*Title\s*\|\s*Model\s*\|',
        re.IGNORECASE
    )

    # Pattern for 5-column rows
    TABLE_ROW_5COL = re.compile(
        r'\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]*)\s*\|\s*([^|]*)\s*\|'
    )

    # Pattern for 4-column rows (no keywords)
    TABLE_ROW_4COL = re.compile(
        r'\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]*)\s*\|'
    )

    # Markdown link pattern
    LINK_PATTERN = re.compile(r'\[([^\]]*)\]\(([^)]+)\)')

    # GitHub URL pattern
    GITHUB_URL_PATTERN = re.compile(
        r'https?://github\.com/([^/\s\)\]"<>]+/[^/\s\)\]"<>]+)',
        re.IGNORECASE
    )

    # arXiv pattern
    ARXIV_PATTERN = re.compile(r'arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})', re.IGNORECASE)

    # Conference patterns
    CONFERENCE_PATTERNS = {
        'CVPR': re.compile(r"CVPR['\s]*(\d{2,4})?", re.IGNORECASE),
        'ECCV': re.compile(r"ECCV['\s]*(\d{2,4})?", re.IGNORECASE),
        'ICCV': re.compile(r"ICCV['\s]*(\d{2,4})?", re.IGNORECASE),
        'NeurIPS': re.compile(r"NeurIPS['\s]*(\d{2,4})?", re.IGNORECASE),
        'ICML': re.compile(r"ICML['\s]*(\d{2,4})?", re.IGNORECASE),
        'ICLR': re.compile(r"ICLR['\s]*(\d{2,4})?", re.IGNORECASE),
        'AAAI': re.compile(r"AAAI['\s]*(\d{2,4})?", re.IGNORECASE),
        'IJCAI': re.compile(r"IJCAI['\s]*(\d{2,4})?", re.IGNORECASE),
        'SIGGRAPH': re.compile(r"SIGGRAPH['\s]*(\d{2,4})?", re.IGNORECASE),
        'WACV': re.compile(r"WACV['\s]*(\d{2,4})?", re.IGNORECASE),
        'BMVC': re.compile(r"BMVC['\s]*(\d{2,4})?", re.IGNORECASE),
        'MICCAI': re.compile(r"MICCAI['\s]*(\d{2,4})?", re.IGNORECASE),
        'ACCV': re.compile(r"ACCV['\s]*(\d{2,4})?", re.IGNORECASE),
        'ACM MM': re.compile(r"ACM\s*MM['\s]*(\d{2,4})?", re.IGNORECASE),
        'TPAMI': re.compile(r"TPAMI['\s]*(\d{2,4})?", re.IGNORECASE),
        'TIP': re.compile(r"TIP['\s]*(\d{2,4})?", re.IGNORECASE),
        'TOG': re.compile(r"TOG['\s]*(\d{2,4})?", re.IGNORECASE),
        'IJCV': re.compile(r"IJCV['\s]*(\d{2,4})?", re.IGNORECASE),
    }

    # Section header pattern
    SECTION_PATTERN = re.compile(r'^##\s+(.+)$', re.MULTILINE)

    # Year pattern
    YEAR_PATTERN = re.compile(r'20\d{2}')

    @classmethod
    def can_parse(cls, content: str, hints: Optional[Dict[str, Any]] = None) -> float:
        """Check if content matches SR table format."""
        if hints and hints.get("parser") == "table_sr":
            return 1.0

        score = 0.0

        # Check for table header with Title and Model columns
        if cls.TABLE_HEADER_PATTERN.search(content):
            score += 0.5

        # Check for Keywords column
        if re.search(r'\|\s*Keywords\s*\|', content, re.IGNORECASE):
            score += 0.3

        # Negative: if has <sub> author tags, probably AIO format
        if re.search(r'<sub>[^<]+</sub>', content):
            score -= 0.2

        return min(max(score, 0.0), 1.0)

    @property
    def capabilities(self) -> ParserCapabilities:
        return ParserCapabilities(
            extracts_title=True,
            extracts_model_name=True,
            extracts_authors=False,
            extracts_year=True,
            extracts_conference=True,
            extracts_github=True,
            extracts_arxiv=True,
            extracts_keywords=True,
        )

    def parse(
        self,
        content: str,
        source_id: str,
        hints: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Parse SR-style markdown tables into entries."""
        entries = []
        current_section = ""
        lines = content.split('\n')
        in_table = False
        timestamp = datetime.now().strftime("%Y-%m-%d")

        skip_sections = hints.get("skip_sections", []) if hints else []

        for line in lines:
            # Check for section headers
            section_match = self.SECTION_PATTERN.match(line)
            if section_match:
                current_section = section_match.group(1).strip()
                in_table = False

                # Skip if section is in skip list
                if any(skip.lower() in current_section.lower() for skip in skip_sections):
                    continue

            # Check for table header
            if self.TABLE_HEADER_PATTERN.search(line):
                in_table = True
                continue

            # Skip separator lines
            if in_table and re.match(r'\|[\s\-:]+\|', line):
                continue

            # Parse table rows
            if in_table and line.strip().startswith('|'):
                entry = self._parse_row(line, current_section, source_id, timestamp)
                if entry:
                    entries.append(entry)

            # End of table detection
            if in_table and not line.strip().startswith('|') and line.strip():
                in_table = False

        return entries

    def _parse_row(
        self,
        row: str,
        section: str,
        source_id: str,
        timestamp: str
    ) -> Optional[Dict[str, Any]]:
        """Parse a single table row."""
        # Try 5-column format first
        match = self.TABLE_ROW_5COL.match(row)
        if not match:
            match = self.TABLE_ROW_4COL.match(row)
            if not match:
                return None

        groups = match.groups()
        title_cell = groups[0].strip()
        model_cell = groups[1].strip()
        published_cell = groups[2].strip()
        code_cell = groups[3].strip() if len(groups) > 3 else ""
        keywords_cell = groups[4].strip() if len(groups) > 4 else ""

        # Extract title (may contain markdown link)
        title, paper_url = self._extract_link(title_cell)
        if not title:
            title = self._clean_text(title_cell)

        # Extract model name
        model_name = self._clean_text(model_cell)
        if not model_name:
            return None

        # Extract conference/year/arxiv
        conference, year, arxiv_id = self._extract_publication_info(published_cell)

        # Get year from section if not found
        if not year:
            year_match = self.YEAR_PATTERN.search(section)
            if year_match:
                year = year_match.group()

        # Get paper URL from published cell if not in title
        if not paper_url:
            _, paper_url = self._extract_link(published_cell)

        # Extract GitHub URL
        github_url = self._extract_github_url(code_cell)
        github_full_name = None
        if github_url:
            github_match = self.GITHUB_URL_PATTERN.search(github_url)
            if github_match:
                github_full_name = github_match.group(1)

        # Extract keywords
        keywords = self._parse_keywords(keywords_cell)

        entry = {
            "title": title,
            "model_name": model_name,
            "authors": [],
            "year": year,
            "conference": conference,
            "arxiv_id": arxiv_id,
            "paper_url": paper_url,
            "github_url": github_url,
            "github_full_name": github_full_name,
            "keywords": keywords,
            "section": section,
            "has_repo": bool(github_url),
            "last_synced": timestamp,
        }

        # Generate unique ID
        entry["id"] = self._generate_entry_id(entry, source_id)

        return entry

    def _extract_link(self, cell: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract text and URL from markdown link."""
        match = self.LINK_PATTERN.search(cell)
        if match:
            return match.group(1).strip(), match.group(2).strip()
        return None, None

    def _extract_publication_info(
        self,
        cell: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Extract conference, year, and arXiv ID."""
        conference = None
        year = None
        arxiv_id = None

        # Check for arXiv
        arxiv_match = self.ARXIV_PATTERN.search(cell)
        if arxiv_match:
            arxiv_id = arxiv_match.group(1)

        # Check for conferences
        for conf_name, pattern in self.CONFERENCE_PATTERNS.items():
            match = pattern.search(cell)
            if match:
                conference = conf_name
                if match.group(1):
                    year_str = match.group(1)
                    if len(year_str) == 2:
                        year = f"20{year_str}"
                    else:
                        year = year_str
                break

        # Find standalone year if not from conference
        if not year:
            year_match = self.YEAR_PATTERN.search(cell)
            if year_match:
                year = year_match.group()

        return conference, year, arxiv_id

    def _extract_github_url(self, cell: str) -> Optional[str]:
        """Extract GitHub URL from cell."""
        # Try markdown link first
        link_match = self.LINK_PATTERN.search(cell)
        if link_match:
            url = link_match.group(2)
            if 'github.com' in url.lower():
                return url

        # Try direct URL
        url_match = self.GITHUB_URL_PATTERN.search(cell)
        if url_match:
            return f"https://github.com/{url_match.group(1)}"

        return None

    def _parse_keywords(self, cell: str) -> List[str]:
        """Parse keywords from comma-separated text."""
        if not cell:
            return []

        cell = self._clean_text(cell)
        if not cell:
            return []

        keywords = re.split(r'[,;/]', cell)
        return [k.strip() for k in keywords if k.strip()]

    def _clean_text(self, text: str) -> str:
        """Remove markdown formatting."""
        text = self.LINK_PATTERN.sub(r'\1', text)
        text = re.sub(r'\*+', '', text)
        text = re.sub(r'_+', '', text)
        text = ' '.join(text.split())
        return text.strip()
