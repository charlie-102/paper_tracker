"""Indexed JSON cache for awesome list entries.

Provides fast search using in-memory indexes built on load.
Storage remains as JSON for simplicity and portability.
"""

import re
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from collections import defaultdict


@dataclass
class SearchQuery:
    """Structured search query for indexed cache."""
    text: Optional[str] = None
    sources: Optional[List[str]] = None
    years: Optional[List[str]] = None
    conferences: Optional[List[str]] = None
    domains: Optional[List[str]] = None
    has_code_only: bool = False
    limit: int = 100
    offset: int = 0


class IndexedCache:
    """JSON cache with in-memory indexes for fast queries.

    Indexes are built on load and updated on write.
    Search uses index intersection for efficient filtering.

    Usage:
        cache = IndexedCache(Path("data/awesome_cache.json"))

        # Add entries
        cache.add_entries(entries, "owner/repo")
        cache.save()

        # Search
        results = cache.search(SearchQuery(text="denoising", years=["2024"]))
    """

    CACHE_VERSION = "2.0"

    def __init__(self, cache_path: Optional[Path] = None):
        """Initialize cache with optional path.

        Args:
            cache_path: Path to JSON cache file. Defaults to data/awesome_cache.json
        """
        self.cache_path = cache_path or Path("data/awesome_cache.json")

        # Primary storage: entry_id -> entry dict
        self.entries: Dict[str, Dict[str, Any]] = {}

        # Indexes (built on load, updated on write)
        self._idx_by_year: Dict[str, Set[str]] = defaultdict(set)
        self._idx_by_conference: Dict[str, Set[str]] = defaultdict(set)
        self._idx_by_source: Dict[str, Set[str]] = defaultdict(set)
        self._idx_by_domain: Dict[str, Set[str]] = defaultdict(set)
        self._idx_has_code: Set[str] = set()

        # Full-text index (token -> entry_ids)
        self._idx_tokens: Dict[str, Set[str]] = defaultdict(set)

        # Metadata
        self.last_updated: Optional[str] = None

        self._load()

    def _load(self):
        """Load cache from JSON file and build indexes."""
        if not self.cache_path.exists():
            return

        try:
            with open(self.cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Failed to load cache: {e}")
            return

        self.last_updated = data.get("last_updated")

        # Handle both v1 and v2 cache formats
        entries_data = data.get("entries", {})

        # v1 format has nested structure, v2 is flat
        if isinstance(entries_data, dict):
            for entry_id, entry in entries_data.items():
                if isinstance(entry, dict):
                    self.entries[entry_id] = entry
                    self._index_entry(entry_id, entry)

    def _index_entry(self, entry_id: str, entry: Dict[str, Any]):
        """Add entry to all indexes."""
        # Year index
        year = entry.get("year")
        if year:
            self._idx_by_year[str(year)].add(entry_id)

        # Conference index (normalize to uppercase)
        conference = entry.get("conference")
        if conference:
            self._idx_by_conference[conference.upper()].add(entry_id)

        # Source index
        source = entry.get("source_list", "")
        if source:
            self._idx_by_source[source].add(entry_id)

        # Domain index
        domain = entry.get("domain", "")
        if domain:
            self._idx_by_domain[domain].add(entry_id)

        # Has code index
        if entry.get("has_repo") or entry.get("github_url"):
            self._idx_has_code.add(entry_id)

        # Full-text index
        tokens = self._tokenize(entry)
        for token in tokens:
            self._idx_tokens[token].add(entry_id)

    def _unindex_entry(self, entry_id: str, entry: Dict[str, Any]):
        """Remove entry from all indexes."""
        year = entry.get("year")
        if year and entry_id in self._idx_by_year.get(str(year), set()):
            self._idx_by_year[str(year)].discard(entry_id)

        conference = entry.get("conference")
        if conference:
            self._idx_by_conference[conference.upper()].discard(entry_id)

        source = entry.get("source_list", "")
        if source:
            self._idx_by_source[source].discard(entry_id)

        domain = entry.get("domain", "")
        if domain:
            self._idx_by_domain[domain].discard(entry_id)

        self._idx_has_code.discard(entry_id)

        tokens = self._tokenize(entry)
        for token in tokens:
            self._idx_tokens[token].discard(entry_id)

    def _tokenize(self, entry: Dict[str, Any]) -> Set[str]:
        """Extract searchable tokens from entry."""
        text_parts = [
            entry.get("title", ""),
            entry.get("model_name", ""),
            " ".join(entry.get("keywords", []) or []),
            entry.get("section", ""),
            " ".join(entry.get("authors", []) or []),
        ]
        text = " ".join(str(p) for p in text_parts if p).lower()

        # Tokenize: extract words with 2+ characters
        tokens = set(re.findall(r'\w{2,}', text))
        return tokens

    def search(self, query: SearchQuery) -> List[Dict[str, Any]]:
        """
        Search entries using indexes for fast filtering.

        Strategy:
        1. Start with smallest applicable index set
        2. Intersect with other index sets
        3. Apply text filter last (most expensive)
        4. Sort and paginate
        """
        candidate_ids: Optional[Set[str]] = None

        # Filter by source (usually smallest set)
        if query.sources:
            source_ids: Set[str] = set()
            for source in query.sources:
                source_ids.update(self._idx_by_source.get(source, set()))
            candidate_ids = source_ids

        # Filter by year
        if query.years:
            year_ids: Set[str] = set()
            for year in query.years:
                year_ids.update(self._idx_by_year.get(str(year), set()))
            candidate_ids = year_ids if candidate_ids is None else candidate_ids & year_ids

        # Filter by conference
        if query.conferences:
            conf_ids: Set[str] = set()
            for conf in query.conferences:
                conf_ids.update(self._idx_by_conference.get(conf.upper(), set()))
            candidate_ids = conf_ids if candidate_ids is None else candidate_ids & conf_ids

        # Filter by domain
        if query.domains:
            domain_ids: Set[str] = set()
            for domain in query.domains:
                domain_ids.update(self._idx_by_domain.get(domain, set()))
            candidate_ids = domain_ids if candidate_ids is None else candidate_ids & domain_ids

        # Filter by has_code
        if query.has_code_only:
            candidate_ids = self._idx_has_code.copy() if candidate_ids is None else candidate_ids & self._idx_has_code

        # If no filters, use all entries
        if candidate_ids is None:
            candidate_ids = set(self.entries.keys())

        # Text search (most expensive, do last)
        if query.text:
            text_tokens = set(query.text.lower().split())
            text_ids: Set[str] = set()

            for token in text_tokens:
                # Prefix matching for partial search
                for idx_token, ids in self._idx_tokens.items():
                    if idx_token.startswith(token) or token in idx_token:
                        text_ids.update(ids)

            candidate_ids = candidate_ids & text_ids

        # Get full entries for candidates
        results = [self.entries[eid] for eid in candidate_ids if eid in self.entries]

        # Sort by relevance (has_code first, then by year desc, then by model name)
        def sort_key(e: Dict[str, Any]) -> tuple:
            has_code = not e.get("has_repo", False)  # False sorts before True
            year = -(int(e.get("year") or 0))
            name = (e.get("model_name") or "").lower()
            return (has_code, year, name)

        results.sort(key=sort_key)

        # Paginate
        return results[query.offset:query.offset + query.limit]

    def add_entries(
        self,
        entries: List[Dict[str, Any]],
        source: str,
        domain: Optional[str] = None,
        subtopics: Optional[List[str]] = None
    ):
        """Add or update entries from a source.

        Args:
            entries: List of entry dicts from parser
            source: Source repo identifier (e.g., "owner/repo")
            domain: Optional domain tag (e.g., "image_restoration")
            subtopics: Optional subtopic tags
        """
        for entry in entries:
            entry_id = entry.get("id")
            if not entry_id:
                # Generate ID if not provided
                source_short = source.split('/')[-1].lower().replace('awesome-', '').replace('-', '_')
                model_name = entry.get("model_name", "unknown").lower().replace(' ', '_')
                entry_id = f"{source_short}:{model_name}"
                entry["id"] = entry_id

            entry["source_list"] = source

            # Add domain metadata if provided
            if domain:
                entry["domain"] = domain
            if subtopics:
                entry["subtopics"] = subtopics

            # Remove from old indexes if updating
            if entry_id in self.entries:
                self._unindex_entry(entry_id, self.entries[entry_id])

            # Add to storage and indexes
            self.entries[entry_id] = entry
            self._index_entry(entry_id, entry)

        self.last_updated = datetime.now().isoformat()

    def remove_source(self, source: str):
        """Remove all entries from a specific source."""
        entry_ids = list(self._idx_by_source.get(source, set()))
        for entry_id in entry_ids:
            if entry_id in self.entries:
                self._unindex_entry(entry_id, self.entries[entry_id])
                del self.entries[entry_id]

    def save(self):
        """Save cache to JSON file."""
        data = {
            "version": self.CACHE_VERSION,
            "last_updated": self.last_updated,
            "entry_count": len(self.entries),
            "entries": self.entries,
        }

        # Ensure directory exists
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.cache_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about cached data."""
        return {
            "total_entries": len(self.entries),
            "entries_with_code": len(self._idx_has_code),
            "by_year": {k: len(v) for k, v in sorted(self._idx_by_year.items(), reverse=True)},
            "by_conference": {k: len(v) for k, v in sorted(self._idx_by_conference.items())},
            "by_source": {k: len(v) for k, v in self._idx_by_source.items()},
            "by_domain": {k: len(v) for k, v in self._idx_by_domain.items()},
            "last_updated": self.last_updated,
        }

    def get_entry(self, entry_id: str) -> Optional[Dict[str, Any]]:
        """Get a single entry by ID."""
        return self.entries.get(entry_id)

    def get_entries_by_source(self, source: str) -> List[Dict[str, Any]]:
        """Get all entries from a specific source."""
        entry_ids = self._idx_by_source.get(source, set())
        return [self.entries[eid] for eid in entry_ids if eid in self.entries]

    def clear(self):
        """Clear all entries and indexes."""
        self.entries.clear()
        self._idx_by_year.clear()
        self._idx_by_conference.clear()
        self._idx_by_source.clear()
        self._idx_by_domain.clear()
        self._idx_has_code.clear()
        self._idx_tokens.clear()
        self.last_updated = None
