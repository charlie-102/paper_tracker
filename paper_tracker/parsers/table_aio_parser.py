"""Parser for All-in-One Image Restoration Survey markdown format.

Handles 4-column format: Paper | Avenue | Link | Code
Paper column contains title and authors separated by <br><sub>authors</sub>
Year sections: ## 2024, ## 2025, etc.
"""

import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from .base_parser import BaseAwesomeParser, ParserCapabilities
from . import ParserRegistry


@ParserRegistry.register
class TableAIOParser(BaseAwesomeParser):
    """Parser for All-in-One Image Restoration Survey format.

    Expected format:
    | Paper | Avenue | Link | Code |
    |-------|--------|------|------|
    | Title <br><sub>Authors</sub> | CVPR 2024 | [Paper](url) | [Code](url) |
    """

    name = "table_aio"
    version = "1.0.0"

    # Table header pattern
    TABLE_HEADER_PATTERN = re.compile(
        r'\|\s*Paper\s*\|\s*(?:Avenue|Venue)\s*\|',
        re.IGNORECASE
    )

    # 4-column row pattern
    TABLE_ROW_PATTERN = re.compile(
        r'\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]*)\s*\|'
    )

    # Extract title and authors from cell with <sub> tags
    TITLE_AUTHORS_PATTERN = re.compile(
        r'^(.+?)\s*(?:<br>)?\s*<sub>([^<]+)</sub>',
        re.IGNORECASE | re.DOTALL
    )

    # Year section header
    YEAR_SECTION_PATTERN = re.compile(r'^##\s*(20\d{2})\s*$', re.MULTILINE)

    # Markdown link pattern
    LINK_PATTERN = re.compile(r'\[([^\]]*)\]\(([^)]+)\)')

    # GitHub URL pattern
    GITHUB_URL_PATTERN = re.compile(
        r'https?://github\.com/([^/\s\)\]"<>]+/[^/\s\)\]"<>]+)',
        re.IGNORECASE
    )

    # arXiv pattern
    ARXIV_PATTERN = re.compile(r'arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})', re.IGNORECASE)

    # Conference/venue patterns
    VENUE_PATTERNS = {
        'CVPR': re.compile(r"CVPR\s*(\d{4})?", re.IGNORECASE),
        'ECCV': re.compile(r"ECCV\s*(\d{4})?", re.IGNORECASE),
        'ICCV': re.compile(r"ICCV\s*(\d{4})?", re.IGNORECASE),
        'NeurIPS': re.compile(r"NeurIPS\s*(\d{4})?", re.IGNORECASE),
        'ICML': re.compile(r"ICML\s*(\d{4})?", re.IGNORECASE),
        'ICLR': re.compile(r"ICLR\s*(\d{4})?", re.IGNORECASE),
        'AAAI': re.compile(r"AAAI\s*(\d{4})?", re.IGNORECASE),
        'IJCAI': re.compile(r"IJCAI\s*(\d{4})?", re.IGNORECASE),
        'SIGGRAPH': re.compile(r"SIGGRAPH\s*(\d{4})?", re.IGNORECASE),
        'WACV': re.compile(r"WACV\s*(\d{4})?", re.IGNORECASE),
        'BMVC': re.compile(r"BMVC\s*(\d{4})?", re.IGNORECASE),
        'MICCAI': re.compile(r"MICCAI\s*(\d{4})?", re.IGNORECASE),
        'ACCV': re.compile(r"ACCV\s*(\d{4})?", re.IGNORECASE),
        'ACM MM': re.compile(r"(?:ACM\s*)?MM\s*(\d{4})?", re.IGNORECASE),
        'TPAMI': re.compile(r"T-?PAMI\s*(\d{4})?", re.IGNORECASE),
        'TIP': re.compile(r"T-?IP\s*(\d{4})?", re.IGNORECASE),
        'TOG': re.compile(r"TOG\s*(\d{4})?", re.IGNORECASE),
        'IJCV': re.compile(r"IJCV\s*(\d{4})?", re.IGNORECASE),
        'TMM': re.compile(r"T-?MM\s*(\d{4})?", re.IGNORECASE),
        'TCSVT': re.compile(r"T-?CSVT\s*(\d{4})?", re.IGNORECASE),
        'arXiv': re.compile(r"arXiv", re.IGNORECASE),
    }

    # Year pattern
    YEAR_PATTERN = re.compile(r'20\d{2}')

    @classmethod
    def can_parse(cls, content: str, hints: Optional[Dict[str, Any]] = None) -> float:
        """Check if content matches All-in-One format."""
        if hints and hints.get("parser") == "table_aio":
            return 1.0

        score = 0.0

        # Check for <sub> tags in tables (author format)
        if re.search(r'\|[^|]+<sub>[^<]+</sub>', content):
            score += 0.4

        # Check for year section headers (## 2024, ## 2023, etc.)
        year_sections = cls.YEAR_SECTION_PATTERN.findall(content)
        if len(year_sections) >= 2:
            score += 0.3

        # Check for "Avenue" or "Paper" column header
        if cls.TABLE_HEADER_PATTERN.search(content):
            score += 0.2

        # Negative: if has "Keywords" or "Model" column, probably SR format
        if re.search(r'\|\s*Keywords\s*\|', content, re.IGNORECASE):
            score -= 0.3
        if re.search(r'\|\s*Model\s*\|', content, re.IGNORECASE):
            score -= 0.2

        return min(max(score, 0.0), 1.0)

    @property
    def capabilities(self) -> ParserCapabilities:
        return ParserCapabilities(
            extracts_title=True,
            extracts_model_name=True,  # Derived from title
            extracts_authors=True,
            extracts_year=True,
            extracts_conference=True,
            extracts_github=True,
            extracts_arxiv=True,
            extracts_keywords=False,
        )

    def parse(
        self,
        content: str,
        source_id: str,
        hints: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Parse All-in-One format into entries."""
        entries = []
        current_year = None
        lines = content.split('\n')
        in_paper_table = False
        timestamp = datetime.now().strftime("%Y-%m-%d")

        skip_sections = hints.get("skip_sections", []) if hints else []

        for line in lines:
            # Track year sections
            year_match = self.YEAR_SECTION_PATTERN.match(line)
            if year_match:
                current_year = year_match.group(1)
                in_paper_table = False
                continue

            # Detect paper table headers
            if self.TABLE_HEADER_PATTERN.search(line):
                in_paper_table = True
                continue

            # Skip benchmark/performance tables (contain PSNR, SSIM, etc.)
            if any(x in line for x in ['PSNR', 'SSIM', 'Dataset', 'Method', 'Rain100']):
                if '|' in line and not '<sub>' in line:
                    in_paper_table = False
                    continue

            # Check if we should skip based on skip_sections
            if any(skip.lower() in line.lower() for skip in skip_sections):
                in_paper_table = False
                continue

            # Skip separator lines
            if re.match(r'\|[\s\-:]+\|', line):
                continue

            # Parse table rows
            if in_paper_table and line.strip().startswith('|'):
                entry = self._parse_row(line, current_year, source_id, timestamp)
                if entry:
                    entries.append(entry)

            # End of table detection (non-table content)
            if in_paper_table and not line.strip().startswith('|') and line.strip():
                # Don't end table for section headers or empty lines
                if not line.startswith('#') and not line.startswith('<'):
                    in_paper_table = False

        return entries

    def _parse_row(
        self,
        row: str,
        year: Optional[str],
        source_id: str,
        timestamp: str
    ) -> Optional[Dict[str, Any]]:
        """Parse a single table row."""
        match = self.TABLE_ROW_PATTERN.match(row)
        if not match:
            return None

        paper_cell, venue_cell, link_cell, code_cell = match.groups()

        # Extract title and authors
        title, authors = self._extract_title_authors(paper_cell)
        if not title:
            return None

        # Generate model name from title
        model_name = self._derive_model_name(title)

        # Extract venue/conference and year from venue cell
        conference, venue_year = self._extract_venue(venue_cell)

        # Use venue year if available, otherwise section year
        entry_year = venue_year or year

        # Extract paper URL and arXiv ID
        paper_url, arxiv_id = self._extract_paper_link(link_cell)

        # Extract GitHub URL
        github_url, github_full_name = self._extract_github(code_cell)

        entry = {
            "title": title,
            "model_name": model_name,
            "authors": authors,
            "year": entry_year,
            "conference": conference,
            "arxiv_id": arxiv_id,
            "paper_url": paper_url,
            "github_url": github_url,
            "github_full_name": github_full_name,
            "keywords": [],
            "section": f"{year}" if year else "",
            "has_repo": bool(github_url),
            "last_synced": timestamp,
        }

        # Generate unique ID
        entry["id"] = self._generate_entry_id(entry, source_id)

        return entry

    def _extract_title_authors(self, cell: str) -> Tuple[Optional[str], List[str]]:
        """Extract title and authors from paper cell.

        Format: Title <br><sub>Author1, Author2</sub>
        """
        cell = cell.strip()

        # Try to match title with authors in <sub> tags
        match = self.TITLE_AUTHORS_PATTERN.match(cell)
        if match:
            title = match.group(1).strip()
            authors_str = match.group(2).strip()

            # Clean title (remove any remaining HTML)
            title = re.sub(r'<[^>]+>', '', title).strip()

            # Parse authors (comma-separated)
            authors = [a.strip() for a in authors_str.split(',') if a.strip()]

            return title, authors

        # No <sub> tags - just title
        title = re.sub(r'<[^>]+>', '', cell).strip()
        return title if title else None, []

    def _derive_model_name(self, title: str) -> str:
        """Derive model name from paper title.

        Strategies:
        1. Look for acronym in the title (e.g., "ClearAIR: A Human-Visual...")
        2. Look for known patterns (e.g., "XXXNet", "XXXFormer")
        3. Use first word otherwise
        """
        # Check for colon-separated name (e.g., "ModelName: Description")
        if ':' in title:
            prefix = title.split(':')[0].strip()
            # If prefix is short and uppercase-heavy, it's likely a model name
            if len(prefix) <= 20 and sum(1 for c in prefix if c.isupper()) >= 2:
                return prefix

        # Look for common model name patterns
        patterns = [
            r'\b([A-Z][a-zA-Z]*(?:Net|Former|GAN|SR|IR|Diff))\b',  # SwinIR, RestoreFormer
            r'\b([A-Z]{2,}[a-zA-Z]*)\b',  # ESRGAN, NAFNet (acronym-style)
        ]

        for pattern in patterns:
            match = re.search(pattern, title)
            if match:
                return match.group(1)

        # Default: use first word(s) up to certain length
        words = title.split()
        if words:
            first_word = words[0]
            if len(first_word) <= 15:
                return first_word

        return title[:20] if title else "Unknown"

    def _extract_venue(self, cell: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract venue/conference and year from venue cell."""
        cell = cell.strip()

        # Try each venue pattern
        for venue_name, pattern in self.VENUE_PATTERNS.items():
            match = pattern.search(cell)
            if match:
                year = match.group(1) if match.lastindex and match.group(1) else None
                return venue_name, year

        # Try to extract standalone year
        year_match = self.YEAR_PATTERN.search(cell)
        year = year_match.group() if year_match else None

        return None, year

    def _extract_paper_link(self, cell: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract paper URL and arXiv ID from link cell."""
        paper_url = None
        arxiv_id = None

        # Extract URL from markdown link
        link_match = self.LINK_PATTERN.search(cell)
        if link_match:
            paper_url = link_match.group(2).strip()

        # Extract arXiv ID
        if paper_url:
            arxiv_match = self.ARXIV_PATTERN.search(paper_url)
            if arxiv_match:
                arxiv_id = arxiv_match.group(1)

        return paper_url, arxiv_id

    def _extract_github(self, cell: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract GitHub URL and full name from code cell."""
        cell = cell.strip()

        # Check for markdown link
        link_match = self.LINK_PATTERN.search(cell)
        if link_match:
            url = link_match.group(2).strip()
            if 'github.com' in url.lower():
                # Extract owner/repo
                github_match = self.GITHUB_URL_PATTERN.search(url)
                if github_match:
                    return url, github_match.group(1)
                return url, None

        # Check for direct URL
        github_match = self.GITHUB_URL_PATTERN.search(cell)
        if github_match:
            full_name = github_match.group(1)
            return f"https://github.com/{full_name}", full_name

        return None, None
