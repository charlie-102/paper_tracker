"""Abstract base class for awesome list parsers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class ParserCapabilities:
    """Describes what a parser can extract from markdown content."""
    extracts_title: bool = True
    extracts_model_name: bool = False
    extracts_authors: bool = False
    extracts_year: bool = True
    extracts_conference: bool = True
    extracts_github: bool = True
    extracts_arxiv: bool = True
    extracts_keywords: bool = False


class BaseAwesomeParser(ABC):
    """Abstract base class for awesome list parsers.

    Each parser implementation handles a specific markdown format
    (e.g., different table structures, bullet lists, etc.)
    """

    # Parser identification
    name: str = "base"
    version: str = "1.0.0"

    @classmethod
    @abstractmethod
    def can_parse(cls, content: str, hints: Optional[Dict[str, Any]] = None) -> float:
        """
        Return confidence score (0.0-1.0) that this parser can handle the content.

        Args:
            content: Raw markdown content
            hints: Optional hints from source registry (format, columns, etc.)

        Returns:
            Confidence score. 0.0 = cannot parse, 1.0 = definitely can parse
        """
        pass

    @abstractmethod
    def parse(
        self,
        content: str,
        source_id: str,
        hints: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Parse markdown content into paper entries.

        Args:
            content: Raw markdown content
            source_id: Source repository identifier (e.g., "owner/repo")
            hints: Optional parsing hints (skip_sections, etc.)

        Returns:
            List of entry dicts with keys like:
            - title, model_name, authors, year, conference
            - arxiv_id, paper_url, github_url, github_full_name
            - keywords, section, has_repo
        """
        pass

    @property
    @abstractmethod
    def capabilities(self) -> ParserCapabilities:
        """Return what this parser can extract."""
        pass

    def _generate_entry_id(self, entry: Dict[str, Any], source_id: str) -> str:
        """Generate a unique ID for an entry.

        Format: {source_short}:{identifier}
        """
        source_short = source_id.split('/')[-1].lower().replace('awesome-', '').replace('-', '_')

        # Use model_name if available, otherwise derive from title
        identifier = entry.get('model_name', '')
        if not identifier and entry.get('title'):
            # Use first meaningful word from title
            title_words = entry['title'].split()
            identifier = title_words[0] if title_words else 'unknown'

        identifier = identifier.lower().replace(' ', '_').replace('-', '_')
        # Remove special characters
        identifier = ''.join(c for c in identifier if c.isalnum() or c == '_')

        return f"{source_short}:{identifier}"
