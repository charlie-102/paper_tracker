"""Manager for awesome list data - syncing, caching, and searching.

Uses the parser plugin system for different markdown formats and
indexed cache for efficient search.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .github_client import GitHubClient
    from .models import AwesomeEntry
    from .cache_manager import IndexedCache, SearchQuery
    from .source_registry import SourceRegistry, SourceConfig
    from .parsers import ParserRegistry
except ImportError:
    from github_client import GitHubClient
    from models import AwesomeEntry
    from cache_manager import IndexedCache, SearchQuery
    from source_registry import SourceRegistry, SourceConfig
    from parsers import ParserRegistry


# Default paths
DATA_DIR = Path(__file__).parent.parent / "data"
DEFAULT_CACHE_FILE = DATA_DIR / "awesome_cache.json"


class AwesomeListManager:
    """Manage fetching, caching, and searching awesome list entries.

    Features:
    - Parser plugin system for different markdown formats
    - Indexed JSON cache for fast search
    - Source registry for configuration management
    """

    def __init__(self, cache_path: Optional[Path] = None):
        """
        Initialize the manager.

        Args:
            cache_path: Path to cache file. Uses default if not specified.
        """
        self.cache_path = cache_path or DEFAULT_CACHE_FILE
        self.github = GitHubClient()
        self.cache = IndexedCache(self.cache_path)
        self.registry = SourceRegistry()

    def sync_list(self, repo_full_name: str, force: bool = False) -> int:
        """
        Sync a single awesome list from GitHub.

        Args:
            repo_full_name: e.g., "ChaofWang/Awesome-Super-Resolution"
            force: If True, fetch even if recently synced

        Returns:
            Number of entries synced
        """
        # Get source configuration
        source = self.registry.get_source(repo_full_name)
        if not source:
            # Create minimal config for unknown sources
            source = SourceConfig(
                repo=repo_full_name,
                name=repo_full_name.split("/")[-1]
            )

        # Check if we should skip (recently synced)
        if not force and not self.registry.needs_sync(source):
            return 0

        # Fetch README from GitHub
        parts = repo_full_name.split("/")
        if len(parts) != 2:
            print(f"Invalid repo name: {repo_full_name}")
            return 0

        owner, repo = parts
        print(f"Fetching README from {repo_full_name}...")
        readme = self.github.get_readme(owner, repo)

        if not readme:
            print(f"Could not fetch README from {repo_full_name}")
            self.registry.update_source_state(
                repo_full_name, 0, "Failed to fetch README"
            )
            self.registry.save_state()
            return 0

        # Get parser hints from source config
        hints = self.registry.get_parser_hints(repo_full_name)

        # Select parser (explicit or auto-detect)
        try:
            if source.parser:
                parser_class = ParserRegistry.get_parser(source.parser)
                if parser_class:
                    parser = parser_class()
                else:
                    print(f"Unknown parser '{source.parser}', using auto-detect")
                    parser = ParserRegistry.auto_select(readme, hints)
            else:
                parser = ParserRegistry.auto_select(readme, hints)

            print(f"Using parser: {parser.name} v{parser.version}")
        except ValueError as e:
            print(f"No suitable parser found for {repo_full_name}: {e}")
            self.registry.update_source_state(
                repo_full_name, 0, str(e)
            )
            self.registry.save_state()
            return 0

        # Parse markdown
        entries = parser.parse(readme, repo_full_name, hints)
        print(f"Parsed {len(entries)} entries from {repo_full_name}")

        # Add to cache with domain metadata
        self.cache.add_entries(
            entries,
            source=repo_full_name,
            domain=source.domain,
            subtopics=source.subtopics
        )
        self.cache.save()

        # Update source state
        self.registry.update_source_state(repo_full_name, len(entries))
        self.registry.save_state()

        return len(entries)

    def sync_all(self, force: bool = False) -> Dict[str, int]:
        """
        Sync all configured awesome lists.

        Args:
            force: If True, fetch all lists regardless of sync time

        Returns:
            Dict mapping source names to number of entries
        """
        results = {}

        for source in self.registry.list_enabled():
            try:
                results[source.repo] = self.sync_list(source.repo, force)
            except Exception as e:
                print(f"Error syncing {source.repo}: {e}")
                results[source.repo] = -1
                self.registry.update_source_state(source.repo, 0, str(e))

        self.registry.save_state()
        return results

    def search(
        self,
        query: str = "",
        sources: Optional[List[str]] = None,
        conference: Optional[str] = None,
        year: Optional[str] = None,
        has_code_only: bool = False,
        domain: Optional[str] = None,
        limit: int = 100,
    ) -> List[AwesomeEntry]:
        """
        Search entries in cached awesome lists.

        Args:
            query: Search query (matches title, model name, keywords, authors)
            sources: Filter by source lists (None = all)
            conference: Filter by conference
            year: Filter by year
            has_code_only: Only return entries with GitHub links
            domain: Filter by domain (e.g., "image_restoration")
            limit: Maximum results to return

        Returns:
            List of matching AwesomeEntry objects
        """
        search_query = SearchQuery(
            text=query if query else None,
            sources=sources,
            years=[year] if year else None,
            conferences=[conference] if conference else None,
            domains=[domain] if domain else None,
            has_code_only=has_code_only,
            limit=limit,
        )

        results = self.cache.search(search_query)

        # Convert to AwesomeEntry objects
        return [AwesomeEntry.from_dict(r) for r in results]

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about cached entries."""
        return self.cache.get_stats()

    def get_configured_sources(self) -> List[Dict[str, Any]]:
        """Get list of configured awesome list sources with their status."""
        sources = []

        for source in self.registry.list_all():
            sources.append({
                "repo": source.repo,
                "name": source.name,
                "enabled": source.enabled,
                "parser": source.parser or "auto",
                "domain": source.domain,
                "entry_count": source.entry_count,
                "last_synced": source.last_synced or "Never",
                "last_error": source.last_error,
            })

        return sources

    def to_search_results(
        self,
        entries: List[AwesomeEntry],
        include_no_code: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Convert awesome entries to search result format compatible with web UI.

        Args:
            entries: List of AwesomeEntry objects
            include_no_code: Include entries without GitHub repos

        Returns:
            List of dicts in search result format
        """
        results = []
        for entry in entries:
            if not include_no_code and not entry.has_repo:
                continue

            result = {
                "full_name": entry.github_full_name or f"paper:{entry.model_name}",
                "name": entry.model_name,
                "url": entry.github_url or entry.paper_url or "",
                "stars": 0,
                "description": entry.title[:200] if entry.title else "",
                "weight_status": "Curated" if entry.has_repo else "Paper Only",
                "conference": entry.conference or "",
                "conference_year": entry.year or "",
                "arxiv_id": entry.arxiv_id or "",
                "source": f"awesome:{entry.source_list.split('/')[-1]}",
                "has_repo": entry.has_repo,
                "domain": entry.domain,
                "authors": entry.authors,
                "_entry_id": entry.id,
            }
            results.append(result)

        return results

    def get_domains(self) -> List[str]:
        """Get list of unique domains from cached entries."""
        stats = self.cache.get_stats()
        return list(stats.get("by_domain", {}).keys())

    # Legacy compatibility
    @property
    def entries(self) -> Dict[str, AwesomeEntry]:
        """Legacy property for backward compatibility."""
        return {
            entry_id: AwesomeEntry.from_dict(entry)
            for entry_id, entry in self.cache.entries.items()
        }

    @property
    def source_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Legacy property for backward compatibility."""
        metadata = {}
        for source in self.registry.list_all():
            metadata[source.repo] = {
                "last_synced": source.last_synced or "",
                "entry_count": source.entry_count,
            }
        return metadata


def get_awesome_manager() -> AwesomeListManager:
    """Get or create the global awesome list manager instance."""
    global _manager
    if '_manager' not in globals():
        _manager = AwesomeListManager()
    return _manager


_manager: Optional[AwesomeListManager] = None
