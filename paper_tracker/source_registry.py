"""Source configuration manager for awesome list repositories.

Loads source configurations from config.yaml and maintains runtime state.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

import yaml


@dataclass
class SourceConfig:
    """Configuration for a single source repository."""

    # Required
    repo: str  # e.g., "Harbinzzy/All-in-One-Image-Restoration-Survey"
    name: str  # Display name

    # Parser settings
    parser: Optional[str] = None  # Explicit parser name (None = auto-detect)
    parser_hints: Dict[str, Any] = field(default_factory=dict)

    # Enable/disable
    enabled: bool = True

    # Section filtering
    skip_sections: List[str] = field(default_factory=list)
    include_sections: List[str] = field(default_factory=list)

    # Domain tags
    domain: str = ""  # e.g., "image_restoration", "super_resolution"
    subtopics: List[str] = field(default_factory=list)

    # Sync settings
    sync_interval_days: int = 7

    # Runtime state (not in config, loaded from state file)
    last_synced: Optional[str] = None
    last_error: Optional[str] = None
    entry_count: int = 0


class SourceRegistry:
    """Manages source repository configurations.

    Loads static config from YAML and runtime state from JSON.
    Provides methods to list, get, and update source configurations.

    Usage:
        registry = SourceRegistry()

        # List enabled sources
        for source in registry.list_enabled():
            print(f"{source.repo}: {source.entry_count} entries")

        # Get specific source
        source = registry.get_source("owner/repo")

        # Update state after sync
        source.entry_count = 150
        source.last_synced = datetime.now().isoformat()
        registry.save_state()
    """

    def __init__(
        self,
        config_path: Optional[Path] = None,
        state_path: Optional[Path] = None
    ):
        """Initialize registry with config and state paths.

        Args:
            config_path: Path to config.yaml. Defaults to paper_tracker/config.yaml
            state_path: Path to runtime state JSON. Defaults to data/source_registry.json
        """
        # Determine base directory
        base_dir = Path(__file__).parent

        self.config_path = config_path or base_dir / "config.yaml"
        self.state_path = state_path or base_dir.parent / "data" / "source_registry.json"

        self.sources: Dict[str, SourceConfig] = {}
        self._load()

    def _load(self):
        """Load sources from config and merge with runtime state."""
        # Load static config from YAML
        if not self.config_path.exists():
            return

        with open(self.config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        if not config:
            return

        # Parse awesome_lists section
        for item in config.get("awesome_lists", []):
            # Handle both string and dict formats
            if isinstance(item, str):
                item = {"repo": item}

            repo = item.get("repo")
            if not repo:
                continue

            self.sources[repo] = SourceConfig(
                repo=repo,
                name=item.get("name", repo.split("/")[-1]),
                enabled=item.get("enabled", True),
                parser=item.get("parser"),
                parser_hints=item.get("parser_hints", {}),
                skip_sections=item.get("skip_sections", []),
                include_sections=item.get("include_sections", []),
                domain=item.get("domain", ""),
                subtopics=item.get("subtopics", []),
                sync_interval_days=config.get("awesome_settings", {}).get(
                    "sync_interval_days", 7
                ),
            )

        # Merge runtime state
        self._load_state()

    def _load_state(self):
        """Load runtime state from JSON file."""
        if not self.state_path.exists():
            return

        try:
            with open(self.state_path, 'r', encoding='utf-8') as f:
                state = json.load(f)
        except (json.JSONDecodeError, IOError):
            return

        for repo, data in state.get("sources", {}).items():
            if repo in self.sources:
                self.sources[repo].last_synced = data.get("last_synced")
                self.sources[repo].last_error = data.get("last_error")
                self.sources[repo].entry_count = data.get("entry_count", 0)

    def save_state(self):
        """Save runtime state to JSON file."""
        state = {
            "last_updated": datetime.now().isoformat(),
            "sources": {
                repo: {
                    "last_synced": src.last_synced,
                    "last_error": src.last_error,
                    "entry_count": src.entry_count,
                }
                for repo, src in self.sources.items()
            }
        }

        # Ensure directory exists
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.state_path, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2)

    def get_source(self, repo: str) -> Optional[SourceConfig]:
        """Get source configuration by repo name.

        Args:
            repo: Repository identifier (e.g., "owner/repo")

        Returns:
            SourceConfig or None if not found
        """
        return self.sources.get(repo)

    def list_all(self) -> List[SourceConfig]:
        """List all configured sources."""
        return list(self.sources.values())

    def list_enabled(self) -> List[SourceConfig]:
        """List enabled sources only."""
        return [s for s in self.sources.values() if s.enabled]

    def needs_sync(self, source: SourceConfig) -> bool:
        """Check if a source needs syncing based on last sync time.

        Args:
            source: Source configuration to check

        Returns:
            True if sync is needed (no last_synced or interval exceeded)
        """
        if not source.last_synced:
            return True

        try:
            last = datetime.fromisoformat(source.last_synced)
            days_since = (datetime.now() - last).days
            return days_since >= source.sync_interval_days
        except (ValueError, TypeError):
            return True

    def update_source_state(
        self,
        repo: str,
        entry_count: int,
        error: Optional[str] = None
    ):
        """Update source state after sync.

        Args:
            repo: Repository identifier
            entry_count: Number of entries synced
            error: Error message if sync failed
        """
        source = self.get_source(repo)
        if not source:
            return

        source.last_synced = datetime.now().isoformat()
        source.entry_count = entry_count
        source.last_error = error

    def add_source(self, config: SourceConfig):
        """Add a new source configuration.

        Note: This only adds to runtime. To persist, update config.yaml.

        Args:
            config: Source configuration to add
        """
        self.sources[config.repo] = config

    def get_parser_hints(self, repo: str) -> Dict[str, Any]:
        """Get parser hints for a source.

        Combines explicit parser_hints with source metadata
        that parsers might use.

        Args:
            repo: Repository identifier

        Returns:
            Dict of parser hints
        """
        source = self.get_source(repo)
        if not source:
            return {}

        hints = dict(source.parser_hints)
        hints["parser"] = source.parser
        hints["skip_sections"] = source.skip_sections
        hints["include_sections"] = source.include_sections

        return hints
