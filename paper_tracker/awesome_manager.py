"""Manager for awesome list data - syncing, caching, and searching."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .github_client import GitHubClient
    from .awesome_parser import AwesomeListParser
    from .models import AwesomeEntry
    from .config_loader import config
except ImportError:
    from github_client import GitHubClient
    from awesome_parser import AwesomeListParser
    from models import AwesomeEntry
    from config_loader import config


# Default paths
DATA_DIR = Path(__file__).parent.parent / "data"
DEFAULT_CACHE_FILE = DATA_DIR / "awesome_cache.json"


class AwesomeListManager:
    """Manage fetching, caching, and searching awesome list entries."""

    def __init__(self, cache_path: Optional[Path] = None):
        """
        Initialize the manager.

        Args:
            cache_path: Path to cache file. Uses default if not specified.
        """
        self.cache_path = cache_path or DEFAULT_CACHE_FILE
        self.github = GitHubClient()
        self.parser = AwesomeListParser()
        self.entries: Dict[str, AwesomeEntry] = {}
        self.source_metadata: Dict[str, Dict[str, Any]] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        """Load cached entries from JSON file."""
        if not self.cache_path.exists():
            return

        try:
            with open(self.cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Load source metadata
            self.source_metadata = data.get("sources", {})

            # Load entries
            entries_data = data.get("entries", {})
            for entry_id, entry_dict in entries_data.items():
                self.entries[entry_id] = AwesomeEntry.from_dict(entry_dict)

        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load awesome cache: {e}")

    def _save_cache(self) -> None:
        """Save entries to JSON cache file."""
        # Ensure data directory exists
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "last_updated": datetime.now().isoformat(),
            "sources": self.source_metadata,
            "entries": {
                entry_id: entry.to_dict()
                for entry_id, entry in self.entries.items()
            }
        }

        with open(self.cache_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def sync_list(self, repo_full_name: str, force: bool = False) -> int:
        """
        Sync a single awesome list from GitHub.

        Args:
            repo_full_name: e.g., "ChaofWang/Awesome-Super-Resolution"
            force: If True, fetch even if recently synced

        Returns:
            Number of new/updated entries
        """
        # Check if we should skip (recently synced)
        if not force and repo_full_name in self.source_metadata:
            last_synced_str = self.source_metadata[repo_full_name].get("last_synced", "")
            if last_synced_str:
                try:
                    last_synced = datetime.fromisoformat(last_synced_str)
                    sync_interval = config.get("awesome_settings", {}).get(
                        "sync_interval_days", 7
                    )
                    if datetime.now() - last_synced < timedelta(days=sync_interval):
                        return 0
                except ValueError:
                    pass

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
            return 0

        # Parse markdown tables
        new_entries = self.parser.parse_readme(readme, repo_full_name)
        print(f"Parsed {len(new_entries)} entries from {repo_full_name}")

        # Update entries
        updated_count = 0
        for entry in new_entries:
            if entry.id not in self.entries:
                updated_count += 1
            self.entries[entry.id] = entry

        # Update source metadata
        self.source_metadata[repo_full_name] = {
            "last_synced": datetime.now().isoformat(),
            "entry_count": len(new_entries),
            "entries_with_code": sum(1 for e in new_entries if e.has_repo),
        }

        # Save to cache
        self._save_cache()

        return updated_count

    def sync_all(self, force: bool = False) -> Dict[str, int]:
        """
        Sync all configured awesome lists.

        Args:
            force: If True, fetch all lists regardless of sync time

        Returns:
            Dict mapping source names to number of updated entries
        """
        awesome_lists = config.get("awesome_lists", [])
        if not awesome_lists:
            print("No awesome lists configured in config.yaml")
            return {}

        results = {}
        for list_config in awesome_lists:
            if isinstance(list_config, dict):
                repo = list_config.get("repo", "")
                enabled = list_config.get("enabled", True)
            else:
                repo = list_config
                enabled = True

            if not enabled:
                continue

            if repo:
                try:
                    results[repo] = self.sync_list(repo, force)
                except Exception as e:
                    print(f"Error syncing {repo}: {e}")
                    results[repo] = -1

        return results

    def search(
        self,
        query: str = "",
        sources: Optional[List[str]] = None,
        conference: Optional[str] = None,
        year: Optional[str] = None,
        has_code_only: bool = False,
    ) -> List[AwesomeEntry]:
        """
        Search entries in cached awesome lists.

        Args:
            query: Search query (matches title, model name, keywords)
            sources: Filter by source lists (None = all)
            conference: Filter by conference
            year: Filter by year
            has_code_only: Only return entries with GitHub links

        Returns:
            List of matching AwesomeEntry objects
        """
        results = []
        query_lower = query.lower() if query else ""

        for entry in self.entries.values():
            # Filter by source
            if sources and entry.source_list not in sources:
                continue

            # Filter by has_code
            if has_code_only and not entry.has_repo:
                continue

            # Filter by conference
            if conference and entry.conference != conference:
                continue

            # Filter by year
            if year and entry.year != year:
                continue

            # Filter by query
            if query_lower:
                searchable = " ".join([
                    entry.title.lower(),
                    entry.model_name.lower(),
                    " ".join(entry.keywords).lower(),
                    entry.section.lower(),
                ])
                if query_lower not in searchable:
                    continue

            results.append(entry)

        # Sort by model name for consistent ordering
        results.sort(key=lambda e: e.model_name.lower())

        return results

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about cached entries."""
        by_source = {}
        by_conference = {}
        by_year = {}

        for entry in self.entries.values():
            # By source
            source_short = entry.source_list.split('/')[-1]
            by_source[source_short] = by_source.get(source_short, 0) + 1

            # By conference
            if entry.conference:
                by_conference[entry.conference] = by_conference.get(entry.conference, 0) + 1

            # By year
            if entry.year:
                by_year[entry.year] = by_year.get(entry.year, 0) + 1

        return {
            "total_entries": len(self.entries),
            "entries_with_code": sum(1 for e in self.entries.values() if e.has_repo),
            "by_source": by_source,
            "by_conference": dict(sorted(by_conference.items())),
            "by_year": dict(sorted(by_year.items(), reverse=True)),
            "sources": list(self.source_metadata.keys()),
            "last_sync": max(
                (m.get("last_synced", "") for m in self.source_metadata.values()),
                default=""
            ),
        }

    def get_configured_sources(self) -> List[Dict[str, Any]]:
        """Get list of configured awesome list sources with their status."""
        awesome_lists = config.get("awesome_lists", [])
        sources = []

        for list_config in awesome_lists:
            if isinstance(list_config, dict):
                repo = list_config.get("repo", "")
                name = list_config.get("name", repo.split('/')[-1])
                enabled = list_config.get("enabled", True)
            else:
                repo = list_config
                name = repo.split('/')[-1]
                enabled = True

            meta = self.source_metadata.get(repo, {})
            sources.append({
                "repo": repo,
                "name": name,
                "enabled": enabled,
                "entry_count": meta.get("entry_count", 0),
                "entries_with_code": meta.get("entries_with_code", 0),
                "last_synced": meta.get("last_synced", "Never"),
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
                "_entry_id": entry.id,
            }
            results.append(result)

        return results


def get_awesome_manager() -> AwesomeListManager:
    """Get or create the global awesome list manager instance."""
    global _manager
    if '_manager' not in globals():
        _manager = AwesomeListManager()
    return _manager


_manager: Optional[AwesomeListManager] = None
