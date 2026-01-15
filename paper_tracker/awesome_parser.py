"""Parser for awesome list markdown files."""

import re
from datetime import datetime
from typing import List, Optional, Tuple

try:
    from .models import AwesomeEntry
except ImportError:
    from models import AwesomeEntry


class AwesomeListParser:
    """Parse markdown tables from awesome list READMEs."""

    # Pattern to detect markdown table headers with paper info
    # Flexible to match tables containing Title column
    TABLE_HEADER_PATTERN = re.compile(
        r'\|\s*Title\s*\|',
        re.IGNORECASE
    )

    # Pattern to extract table rows (5 columns: Title, Model, Published, Code, Keywords)
    TABLE_ROW_PATTERN = re.compile(
        r'\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]*)\s*\|\s*([^|]*)\s*\|'
    )

    # Pattern to extract markdown links [text](url)
    LINK_PATTERN = re.compile(r'\[([^\]]*)\]\(([^)]+)\)')

    # Pattern to extract GitHub URLs
    GITHUB_URL_PATTERN = re.compile(
        r'https?://github\.com/([^/\s\)]+/[^/\s\)]+)',
        re.IGNORECASE
    )

    # Pattern to extract arXiv IDs
    ARXIV_PATTERN = re.compile(r'arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})', re.IGNORECASE)

    # Conference detection patterns
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

    # Section header pattern (e.g., "## 2024", "## Video Super-Resolution")
    SECTION_PATTERN = re.compile(r'^##\s+(.+)$', re.MULTILINE)

    # Year pattern
    YEAR_PATTERN = re.compile(r'20\d{2}')

    def parse_readme(self, content: str, source_list: str) -> List[AwesomeEntry]:
        """
        Parse README content and extract all paper entries.

        Args:
            content: Raw markdown content of the README
            source_list: Source repo name (e.g., "ChaofWang/Awesome-Super-Resolution")

        Returns:
            List of AwesomeEntry objects
        """
        entries = []
        current_section = ""
        lines = content.split('\n')
        in_table = False
        timestamp = datetime.now().strftime("%Y-%m-%d")

        for i, line in enumerate(lines):
            # Check for section headers
            section_match = self.SECTION_PATTERN.match(line)
            if section_match:
                current_section = section_match.group(1).strip()
                in_table = False
                continue

            # Check for table header
            if self.TABLE_HEADER_PATTERN.search(line):
                in_table = True
                continue

            # Skip separator lines (|---|---|)
            if in_table and re.match(r'\|[\s\-:]+\|', line):
                continue

            # Parse table rows
            if in_table and line.strip().startswith('|'):
                entry = self._parse_table_row(line, current_section, source_list, timestamp)
                if entry:
                    entries.append(entry)

            # End of table detection (empty line or non-table content)
            if in_table and not line.strip().startswith('|') and line.strip():
                in_table = False

        return entries

    def _parse_table_row(
        self,
        row: str,
        section: str,
        source_list: str,
        timestamp: str
    ) -> Optional[AwesomeEntry]:
        """
        Parse a single table row into an AwesomeEntry.

        Args:
            row: Single markdown table row
            section: Current section name
            source_list: Source repo name
            timestamp: Sync timestamp

        Returns:
            AwesomeEntry or None if parsing fails
        """
        # Try to match 5-column format first
        match = self.TABLE_ROW_PATTERN.match(row)
        if not match:
            # Try simpler 4-column format (Title, Model, Published, Code)
            simple_pattern = re.compile(
                r'\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]*)\s*\|'
            )
            match = simple_pattern.match(row)
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
            title = title_cell

        # Extract model name
        model_name = self._clean_text(model_cell)
        if not model_name:
            return None

        # Extract conference/year/arxiv from published cell
        conference, year, arxiv_id = self._extract_publication_info(published_cell)

        # If no year found, try to get it from section
        if not year:
            year_match = self.YEAR_PATTERN.search(section)
            if year_match:
                year = year_match.group()

        # Extract paper URL from published cell if not in title
        if not paper_url:
            _, paper_url = self._extract_link(published_cell)

        # Extract GitHub URL from code cell
        github_url = self._extract_github_url(code_cell)
        github_full_name = None
        if github_url:
            github_match = self.GITHUB_URL_PATTERN.search(github_url)
            if github_match:
                github_full_name = github_match.group(1)

        # Extract keywords
        keywords = self._parse_keywords(keywords_cell)

        # Generate unique ID
        source_short = source_list.split('/')[-1].lower().replace('awesome-', '')
        entry_id = f"{source_short}:{model_name.lower().replace(' ', '_')}"

        return AwesomeEntry(
            id=entry_id,
            source_list=source_list,
            title=title,
            model_name=model_name,
            conference=conference,
            year=year,
            arxiv_id=arxiv_id,
            paper_url=paper_url,
            github_url=github_url,
            github_full_name=github_full_name,
            keywords=keywords,
            section=section,
            last_synced=timestamp,
            has_repo=bool(github_url),
        )

    def _extract_link(self, cell: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract text and URL from a markdown link."""
        match = self.LINK_PATTERN.search(cell)
        if match:
            return match.group(1).strip(), match.group(2).strip()
        return None, None

    def _extract_publication_info(
        self, cell: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Extract conference, year, and arXiv ID from the published cell.

        Returns:
            Tuple of (conference, year, arxiv_id)
        """
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
                    # Normalize year (24 -> 2024)
                    if len(year_str) == 2:
                        year = f"20{year_str}"
                    else:
                        year = year_str
                break

        # If no year from conference, try to find standalone year
        if not year:
            year_match = self.YEAR_PATTERN.search(cell)
            if year_match:
                year = year_match.group()

        return conference, year, arxiv_id

    def _extract_github_url(self, cell: str) -> Optional[str]:
        """Extract GitHub URL from a cell."""
        # First try to extract from markdown link
        link_match = self.LINK_PATTERN.search(cell)
        if link_match:
            url = link_match.group(2)
            if 'github.com' in url.lower():
                return url

        # Then try direct URL
        url_match = self.GITHUB_URL_PATTERN.search(cell)
        if url_match:
            return f"https://github.com/{url_match.group(1)}"

        return None

    def _parse_keywords(self, cell: str) -> List[str]:
        """Parse keywords from comma or space-separated text."""
        if not cell:
            return []

        # Clean up the cell
        cell = self._clean_text(cell)
        if not cell:
            return []

        # Split by comma or common separators
        keywords = re.split(r'[,;/]', cell)
        keywords = [k.strip() for k in keywords if k.strip()]

        return keywords

    def _clean_text(self, text: str) -> str:
        """Remove markdown formatting and clean text."""
        # Remove markdown links, keeping just the text
        text = self.LINK_PATTERN.sub(r'\1', text)
        # Remove bold/italic markers
        text = re.sub(r'\*+', '', text)
        text = re.sub(r'_+', '', text)
        # Remove extra whitespace
        text = ' '.join(text.split())
        return text.strip()


def parse_awesome_list(content: str, source_list: str) -> List[AwesomeEntry]:
    """Convenience function to parse an awesome list."""
    parser = AwesomeListParser()
    return parser.parse_readme(content, source_list)
