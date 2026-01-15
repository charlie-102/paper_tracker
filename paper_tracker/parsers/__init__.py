"""Parser plugin system for awesome list markdown formats.

Usage:
    from paper_tracker.parsers import ParserRegistry

    # Auto-select best parser
    parser = ParserRegistry.auto_select(markdown_content)
    entries = parser.parse(content, "owner/repo")

    # Or use specific parser
    parser_class = ParserRegistry.get_parser("table_sr")
    parser = parser_class()
    entries = parser.parse(content, "owner/repo")
"""

from typing import Dict, Type, List, Any, Optional

from .base_parser import BaseAwesomeParser, ParserCapabilities


class ParserRegistry:
    """Registry for parser plugins.

    Parsers register themselves using the @ParserRegistry.register decorator.
    """

    _parsers: Dict[str, Type[BaseAwesomeParser]] = {}

    @classmethod
    def register(cls, parser_class: Type[BaseAwesomeParser]) -> Type[BaseAwesomeParser]:
        """Decorator to register a parser.

        Usage:
            @ParserRegistry.register
            class MyParser(BaseAwesomeParser):
                name = "my_parser"
                ...
        """
        cls._parsers[parser_class.name] = parser_class
        return parser_class

    @classmethod
    def get_parser(cls, name: str) -> Optional[Type[BaseAwesomeParser]]:
        """Get parser class by name.

        Args:
            name: Parser name (e.g., "table_sr", "table_aio")

        Returns:
            Parser class or None if not found
        """
        return cls._parsers.get(name)

    @classmethod
    def auto_select(
        cls,
        content: str,
        hints: Optional[Dict[str, Any]] = None
    ) -> BaseAwesomeParser:
        """
        Auto-select best parser for content based on confidence scores.

        Args:
            content: Raw markdown content
            hints: Optional hints (may include explicit parser name)

        Returns:
            Instance of parser with highest confidence score

        Raises:
            ValueError: If no suitable parser found
        """
        # Check if hints specify a parser explicitly
        if hints and hints.get("parser"):
            parser_class = cls.get_parser(hints["parser"])
            if parser_class:
                return parser_class()

        # Auto-detect by confidence score
        best_parser = None
        best_score = 0.0

        for parser_class in cls._parsers.values():
            score = parser_class.can_parse(content, hints)
            if score > best_score:
                best_score = score
                best_parser = parser_class

        if best_parser is None or best_score < 0.1:
            raise ValueError(
                f"No suitable parser found for content. "
                f"Available parsers: {list(cls._parsers.keys())}"
            )

        return best_parser()

    @classmethod
    def list_parsers(cls) -> List[str]:
        """List all registered parser names."""
        return list(cls._parsers.keys())

    @classmethod
    def get_parser_info(cls) -> List[Dict[str, Any]]:
        """Get info about all registered parsers."""
        info = []
        for name, parser_class in cls._parsers.items():
            info.append({
                "name": name,
                "version": parser_class.version,
                "capabilities": parser_class().capabilities.__dict__
            })
        return info


# Import parsers to register them
# These imports trigger the @ParserRegistry.register decorators
from . import table_sr_parser
from . import table_aio_parser

__all__ = [
    "ParserRegistry",
    "BaseAwesomeParser",
    "ParserCapabilities",
]
