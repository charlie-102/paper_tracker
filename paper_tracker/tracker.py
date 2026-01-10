"""Main tracker module with stateful tracking."""

import json
import csv
import yaml
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set

from .config_loader import config
from .github_client import GitHubClient
from .detectors import WeightDetector, ConferenceDetector, ComingSoonDetector, RelevanceFilter
from .models import RepoInfo, RepoState


@dataclass
class RUCandidate:
    """A candidate repository for RU (Reproducible Unit) generation."""
    url: str
    full_name: str
    arxiv_id: str
    added_at: str
    source: str  # "auto" or "manual"
    status: str  # "pending", "processing", "completed", "skipped"
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "full_name": self.full_name,
            "arxiv_id": self.arxiv_id,
            "added_at": self.added_at,
            "source": self.source,
            "status": self.status,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RUCandidate":
        return cls(
            url=data.get("url", ""),
            full_name=data.get("full_name", ""),
            arxiv_id=data.get("arxiv_id", ""),
            added_at=data.get("added_at", ""),
            source=data.get("source", "auto"),
            status=data.get("status", "pending"),
            notes=data.get("notes", ""),
        )


class RUQueueManager:
    """Manager for RU (Reproducible Unit) candidate queue."""

    def __init__(self, queue_path: str = "data/ru_queue.yaml"):
        self.queue_path = Path(queue_path)
        self.candidates: Dict[str, RUCandidate] = {}  # keyed by full_name
        self._load()

    def _load(self):
        """Load queue from YAML file."""
        if not self.queue_path.exists():
            return

        try:
            with open(self.queue_path, "r") as f:
                data = yaml.safe_load(f)

            if data and data.get("candidates"):
                for item in data["candidates"]:
                    candidate = RUCandidate.from_dict(item)
                    self.candidates[candidate.full_name] = candidate
        except Exception as e:
            print(f"Error loading RU queue: {e}")

    def save(self):
        """Save queue to YAML file."""
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "candidates": [c.to_dict() for c in self.candidates.values()]
        }

        with open(self.queue_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    def should_queue(self, repo_info: RepoInfo) -> bool:
        """Check if a repo meets RU candidate criteria."""
        # Must have HAS_WEIGHTS status
        if repo_info.status != RepoState.HAS_WEIGHTS:
            return False
        # Must have an arXiv ID
        if not repo_info.arxiv_id:
            return False
        # Not already in queue with completed/processing status
        existing = self.candidates.get(repo_info.full_name)
        if existing and existing.status in ("completed", "processing"):
            return False
        return True

    def add_candidate(self, repo_info: RepoInfo, source: str = "auto") -> bool:
        """
        Add a repo to the RU queue if it meets criteria.

        Returns True if added, False if already exists or doesn't meet criteria.
        """
        if source == "auto" and not self.should_queue(repo_info):
            return False

        # For manual additions, only require HAS_WEIGHTS (allow missing arXiv)
        if source == "manual" and repo_info.status != RepoState.HAS_WEIGHTS:
            return False

        # Check if already in queue
        existing = self.candidates.get(repo_info.full_name)
        if existing:
            # Don't re-add if completed or processing
            if existing.status in ("completed", "processing"):
                return False
            # Already pending, no need to re-add
            return False

        candidate = RUCandidate(
            url=repo_info.url,
            full_name=repo_info.full_name,
            arxiv_id=repo_info.arxiv_id or "",
            added_at=datetime.now().isoformat(),
            source=source,
            status="pending",
        )
        self.candidates[repo_info.full_name] = candidate
        repo_info.ru_candidate = True
        return True

    def update_status(self, full_name: str, status: str, notes: str = ""):
        """Update the status of a candidate."""
        if full_name in self.candidates:
            self.candidates[full_name].status = status
            if notes:
                self.candidates[full_name].notes = notes

    def remove_candidate(self, full_name: str) -> bool:
        """Remove a candidate from the queue."""
        if full_name in self.candidates:
            del self.candidates[full_name]
            return True
        return False

    def get_pending(self) -> List[RUCandidate]:
        """Get all pending candidates."""
        return [c for c in self.candidates.values() if c.status == "pending"]

    def list_all(self) -> List[RUCandidate]:
        """Get all candidates."""
        return list(self.candidates.values())


class PaperTracker:
    """Stateful tracker for finding reproducible ML repos."""

    def __init__(self, token: Optional[str] = None, config_path: Optional[str] = None,
                 ru_queue_path: Optional[str] = None):
        # Load config
        config.load(config_path)

        # Initialize components
        self.github = GitHubClient(token)
        self.weight_detector = WeightDetector()
        self.conference_detector = ConferenceDetector()
        self.coming_soon_detector = ComingSoonDetector()
        self.relevance_filter = RelevanceFilter()

        # RU Queue manager
        self.ru_queue = RUQueueManager(ru_queue_path or "data/ru_queue.yaml")

        # Results storage (keyed by full_name)
        self.repos: Dict[str, RepoInfo] = {}

        # Track changes in this run
        self._fresh_releases: List[str] = []  # full_names of fresh releases
        self._new_repos: List[str] = []  # full_names of newly discovered repos
        self._watchlist_updates: List[str] = []  # full_names that changed from COMING_SOON

    def load_history(self, json_path: str) -> bool:
        """
        Load history from JSON file.

        Args:
            json_path: Path to history.json

        Returns:
            True if history was loaded, False if file doesn't exist
        """
        path = Path(json_path)
        if not path.exists():
            print(f"No history file found at {json_path}, starting fresh")
            return False

        try:
            with open(path, "r") as f:
                data = json.load(f)

            # Load repos from history
            for repo_data in data.get("repos", []):
                repo_info = RepoInfo.from_dict(repo_data)
                self.repos[repo_info.full_name] = repo_info

            print(f"Loaded {len(self.repos)} repos from history")

            # Auto-populate RU queue for existing repos that meet criteria
            new_candidates = 0
            for repo_info in self.repos.values():
                if self.ru_queue.should_queue(repo_info):
                    if self.ru_queue.add_candidate(repo_info, source="auto"):
                        new_candidates += 1
            if new_candidates > 0:
                print(f"Added {new_candidates} repos to RU queue")

            return True

        except (json.JSONDecodeError, KeyError) as e:
            print(f"Error loading history: {e}, starting fresh")
            return False

    def save_history(self, json_path: str):
        """
        Save current state to history JSON file.

        Args:
            json_path: Path to save history.json
        """
        path = Path(json_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "last_updated": datetime.now().isoformat(),
            "summary": self.get_summary(),
            "repos": [r.to_dict() for r in self.repos.values()]
        }

        with open(path, "w") as f:
            json.dump(data, f, indent=2)

        print(f"Saved {len(self.repos)} repos to {json_path}")

        # Also save RU queue
        self.ru_queue.save()

    def search(
        self,
        min_stars: Optional[int] = None,
        max_results: Optional[int] = None,
        year_filter: Optional[str] = None,
        queries: Optional[List[str]] = None,
    ) -> List[RepoInfo]:
        """
        Search GitHub with two-pass strategy and delta checking.

        Two passes per query:
        1. sort="stars" - Catch SOTA/Famous repos
        2. sort="updated" - Catch brand new/bleeding edge repos

        Delta check logic:
        - Case A (Stable): In history with HAS_WEIGHTS -> Skip (update last_checked only)
        - Case B (Watchlist): In history with COMING_SOON -> Re-check README
        - Case C (New): Not in history -> Full scan

        Args:
            min_stars: Minimum stars filter
            max_results: Max results per query per pass
            year_filter: Filter repos created after this year
            queries: List of search queries

        Returns:
            List of all RepoInfo objects
        """
        # Use config defaults if not specified
        min_stars = min_stars or config.get("search.min_stars", 10)
        max_results = max_results or config.get("search.max_results_per_query", 20)
        year_filter = year_filter or config.get("search.year_filter", "2024")
        queries = queries or config.queries

        # Reset tracking for this run
        self._fresh_releases = []
        self._new_repos = []
        self._watchlist_updates = []

        # Track which repos we've seen this run (to avoid duplicate processing)
        seen_this_run: Set[str] = set()

        for query in queries:
            print(f"Searching: {query}...")

            # Two-pass search strategy
            all_results = []

            # Pass 1: Sort by stars (catch famous/SOTA repos)
            stars_results = self.github.search_repos(
                query=query,
                min_stars=min_stars,
                created_after=f"{year_filter}-01-01",
                max_results=max_results,
                sort="stars"
            )
            all_results.extend(stars_results)
            print(f"  Pass 1 (stars): {len(stars_results)} results")

            # Pass 2: Sort by updated (catch bleeding edge repos)
            updated_results = self.github.search_repos(
                query=query,
                min_stars=min_stars,
                created_after=f"{year_filter}-01-01",
                max_results=max_results,
                sort="updated"
            )
            all_results.extend(updated_results)
            print(f"  Pass 2 (updated): {len(updated_results)} results")

            # Process all results (deduplicated by full_name)
            for repo_data in all_results:
                full_name = repo_data.get("full_name", "")
                if not full_name or full_name in seen_this_run:
                    continue

                seen_this_run.add(full_name)
                self._process_repo_with_delta(repo_data)

        return list(self.repos.values())

    def _process_repo_with_delta(self, repo_data: Dict):
        """
        Process a repository with delta checking logic.

        Case A (Stable): In history with HAS_WEIGHTS -> Skip (update last_checked only)
        Case B (Watchlist): In history with COMING_SOON -> Re-check README
        Case C (New): Not in history -> Full scan
        """
        full_name = repo_data.get("full_name", "")

        # Check exclusions and relevance first
        if self.relevance_filter.is_excluded(repo_data):
            return
        if not self.relevance_filter.is_relevant(repo_data):
            return

        # Check if repo is in history
        existing = self.repos.get(full_name)

        if existing:
            # Update basic info (stars may have changed)
            existing.stars = repo_data.get("stargazers_count", existing.stars)
            existing.updated_at = repo_data.get("updated_at", "")[:10]

            if existing.status == RepoState.HAS_WEIGHTS:
                # Case A: Stable - skip weight detection but re-run conference detection
                # (Conference info may be added/updated after weights are released)
                owner, name = full_name.split("/")
                readme = self.github.get_readme(owner, name)
                conf_result = self.conference_detector.detect(readme, existing.description)
                existing.conference = conf_result.conference
                existing.conference_year = conf_result.year
                existing.arxiv_id = conf_result.arxiv_id
                existing.conference_details = conf_result.details
                existing.last_checked = datetime.now().strftime("%Y-%m-%d")

                # Check if repo qualifies as RU candidate (now that we have updated arXiv)
                if self.ru_queue.should_queue(existing):
                    if self.ru_queue.add_candidate(existing, source="auto"):
                        print(f"  -> Added to RU queue: {existing.full_name}")
                return

            elif existing.status == RepoState.COMING_SOON:
                # Case B: Watchlist - re-check README for weights
                owner, name = full_name.split("/")
                readme = self.github.get_readme(owner, name)
                self._update_repo_detection(existing, readme)

                if existing.status == RepoState.HAS_WEIGHTS:
                    # Fresh release detected!
                    self._fresh_releases.append(full_name)
                    self._watchlist_updates.append(full_name)
                    print(f"  -> Fresh release: {full_name}")
                return

            else:
                # NO_WEIGHTS - re-check
                owner, name = full_name.split("/")
                readme = self.github.get_readme(owner, name)
                self._update_repo_detection(existing, readme)
                return

        # Case C: New repo - full scan
        repo_info = RepoInfo.from_github_repo(repo_data)

        # Get README and analyze
        owner, name = full_name.split("/")
        readme = self.github.get_readme(owner, name)
        self._update_repo_detection(repo_info, readme)

        # Store the repo
        self.repos[full_name] = repo_info
        self._new_repos.append(full_name)

    def _update_repo_detection(self, repo_info: RepoInfo, readme: str):
        """Update detection results for a repo."""
        # Detect weights
        weight_result = self.weight_detector.detect(readme)
        repo_info.weight_status = weight_result.status
        repo_info.weight_confidence = weight_result.confidence
        repo_info.weight_details = weight_result.details

        # Detect conference
        conf_result = self.conference_detector.detect(readme, repo_info.description)
        repo_info.conference = conf_result.conference
        repo_info.conference_year = conf_result.year
        repo_info.arxiv_id = conf_result.arxiv_id
        repo_info.conference_details = conf_result.details

        # Detect coming soon
        coming_soon_result = self.coming_soon_detector.detect(readme)
        repo_info.coming_soon_detected = coming_soon_result.detected
        repo_info.coming_soon_details = coming_soon_result.details

        # Determine new status
        if weight_result.status != "None":
            new_status = RepoState.HAS_WEIGHTS
        elif coming_soon_result.detected:
            new_status = RepoState.COMING_SOON
        else:
            new_status = RepoState.NO_WEIGHTS

        # Update status (tracks changes)
        repo_info.update_status(new_status)

        # Auto-add to RU queue if criteria met
        if self.ru_queue.should_queue(repo_info):
            if self.ru_queue.add_candidate(repo_info, source="auto"):
                print(f"  -> Added to RU queue: {repo_info.full_name}")

    def get_summary(self) -> Dict:
        """Get summary statistics."""
        repos = list(self.repos.values())

        # Status counts
        status_counts = {}
        for r in repos:
            status_counts[r.status.value] = status_counts.get(r.status.value, 0) + 1

        # Weight status counts
        weight_counts = {}
        for r in repos:
            weight_counts[r.weight_status] = weight_counts.get(r.weight_status, 0) + 1

        # Conference counts
        conf_counts = {}
        for r in repos:
            if r.conference:
                conf_counts[r.conference] = conf_counts.get(r.conference, 0) + 1

        # Fresh releases (last 7 days)
        fresh_releases = [r for r in repos if r.is_fresh_release(days=7)]

        # With weights
        with_weights = sum(1 for r in repos if r.status == RepoState.HAS_WEIGHTS)

        # Coming soon (watchlist)
        coming_soon = sum(1 for r in repos if r.status == RepoState.COMING_SOON)

        # RU queue counts
        ru_pending = len(self.ru_queue.get_pending())
        ru_total = len(self.ru_queue.list_all())

        return {
            "total": len(repos),
            "with_weights": with_weights,
            "coming_soon": coming_soon,
            "fresh_releases": len(fresh_releases),
            "new_this_run": len(self._new_repos),
            "by_status": status_counts,
            "by_weight_status": weight_counts,
            "by_conference": conf_counts,
            "ru_pending": ru_pending,
            "ru_total": ru_total,
            "timestamp": datetime.now().isoformat(),
        }

    def print_results(self, show_details: bool = False):
        """Print results as formatted table."""
        repos = list(self.repos.values())

        # Sort by status priority, then stars
        status_priority = {
            RepoState.HAS_WEIGHTS: 0,
            RepoState.COMING_SOON: 1,
            RepoState.NO_WEIGHTS: 2
        }
        repos_sorted = sorted(
            repos,
            key=lambda r: (status_priority.get(r.status, 3), -r.stars)
        )

        # Print header
        print("\n" + "=" * 120)
        print("PAPER IMPLEMENTATION TRACKER - Low-Level Vision Repos (Stateful)")
        print("=" * 120)

        # Summary
        summary = self.get_summary()
        print(f"\nTotal: {summary['total']} repos tracked")
        print(f"  - With weights (HAS_WEIGHTS): {summary['with_weights']}")
        print(f"  - Coming soon (COMING_SOON): {summary['coming_soon']}")
        print(f"  - Fresh releases (last 7 days): {summary['fresh_releases']}")
        print(f"  - New this run: {summary['new_this_run']}")

        if summary['by_weight_status']:
            print(f"  - By weight source:")
            for status, count in sorted(summary['by_weight_status'].items()):
                if status != "None":
                    print(f"    - {status}: {count}")

        if summary['by_conference']:
            print(f"  - By conference:")
            for conf, count in sorted(summary['by_conference'].items()):
                print(f"    - {conf}: {count}")

        # Print fresh releases first
        fresh = [r for r in repos_sorted if r.is_fresh_release()]
        if fresh:
            print("\n" + "-" * 120)
            print("FRESH RELEASES (weights released in last 7 days)")
            print("-" * 120)
            for repo in fresh:
                print(f"  {repo.name:<30} {repo.stars:>6} stars  {repo.url}")

        # Print table
        print("\n" + "-" * 120)
        print(f"{'Repo Name':<30} {'Stars':>6} {'Status':<12} {'Weights':<10} {'Conf':<10} {'Checked':<12} URL")
        print("-" * 120)

        for repo in repos_sorted:
            conf_display = repo.conference or "-"
            if repo.conference_year:
                conf_display = f"{repo.conference}'{repo.conference_year[-2:]}"

            status_icon = ""
            if repo.is_fresh_release():
                status_icon = " [NEW]"

            print(f"{repo.name[:29]:<30} {repo.stars:>6} {repo.status.value:<12} "
                  f"{repo.weight_status:<10} {conf_display:<10} {repo.last_checked:<12} {repo.url}{status_icon}")

            if show_details:
                if repo.weight_details:
                    for detail in repo.weight_details[:2]:
                        print(f"    -> {detail[:80]}")
                if repo.coming_soon_details:
                    for detail in repo.coming_soon_details[:2]:
                        print(f"    -> {detail[:80]}")
                if repo.arxiv_id:
                    print(f"    -> arXiv: {repo.arxiv_id}")

        print("-" * 120)

    def export_json(self, output_path: str):
        """Export results to JSON."""
        data = {
            "summary": self.get_summary(),
            "repos": [r.to_dict() for r in self.repos.values()]
        }

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(data, f, indent=config.get("output.json_indent", 2))

        print(f"Exported to {output_path}")

    def export_csv(self, output_path: str):
        """Export results to CSV."""
        repos = list(self.repos.values())

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Name", "Full Name", "Stars", "Status", "Weight Status", "Conference",
                "Conference Year", "arXiv ID", "Last Checked", "Status Changed", "URL", "Description"
            ])

            for r in repos:
                writer.writerow([
                    r.name, r.full_name, r.stars, r.status.value, r.weight_status,
                    r.conference or "", r.conference_year or "", r.arxiv_id or "",
                    r.last_checked, r.status_changed_date, r.url, r.description
                ])

        print(f"Exported to {output_path}")

    def export_markdown(self, output_path: str):
        """Export results to Markdown with Fresh Releases section."""
        repos = sorted(self.repos.values(), key=lambda r: -r.stars)
        summary = self.get_summary()

        lines = [
            "# Paper Implementation Tracker Results",
            "",
            f"Generated: {summary['timestamp'][:10]}",
            "",
            "## Summary",
            "",
            f"- **Total repos tracked:** {summary['total']}",
            f"- **With weights:** {summary['with_weights']}",
            f"- **Coming soon (watchlist):** {summary['coming_soon']}",
            f"- **Fresh releases (last 7 days):** {summary['fresh_releases']}",
            f"- **New this run:** {summary['new_this_run']}",
            "",
        ]

        # Fresh Releases section (highlighted at top)
        fresh_releases = [r for r in repos if r.is_fresh_release(days=7)]
        if fresh_releases:
            lines.extend([
                "## Fresh Releases",
                "",
                "Repos where weights were released in the last 7 days:",
                "",
                "| Repo | Stars | Previous Status | Conference | URL |",
                "|------|-------|-----------------|------------|-----|",
            ])
            for r in sorted(fresh_releases, key=lambda x: -x.stars):
                prev = r.previous_status.value if r.previous_status else "new"
                conf = r.conference or "-"
                url = f"[Link]({r.url})"
                lines.append(f"| {r.name[:25]} | {r.stars} | {prev} | {conf} | {url} |")
            lines.append("")

        # Coming Soon (Watchlist) section
        coming_soon = [r for r in repos if r.status == RepoState.COMING_SOON]
        if coming_soon:
            lines.extend([
                "## Watchlist (Coming Soon)",
                "",
                "Repos that have promised weights but not yet released:",
                "",
                "| Repo | Stars | Conference | Promise Details | URL |",
                "|------|-------|------------|-----------------|-----|",
            ])
            for r in sorted(coming_soon, key=lambda x: -x.stars)[:20]:
                conf = r.conference or "-"
                promise = r.coming_soon_details[0][:30] if r.coming_soon_details else "-"
                url = f"[Link]({r.url})"
                lines.append(f"| {r.name[:25]} | {r.stars} | {conf} | {promise} | {url} |")
            lines.append("")

        # All repos with weights
        with_weights = [r for r in repos if r.status == RepoState.HAS_WEIGHTS]
        if with_weights:
            lines.extend([
                "## All Repos with Weights",
                "",
                "| Repo | Stars | Weight Source | Conference | arXiv | URL |",
                "|------|-------|---------------|------------|-------|-----|",
            ])
            for r in sorted(with_weights, key=lambda x: -x.stars):
                conf = r.conference or "-"
                if r.conference_year:
                    conf = f"{r.conference}'{r.conference_year[-2:]}"
                arxiv = f"[{r.arxiv_id}](https://arxiv.org/abs/{r.arxiv_id})" if r.arxiv_id else "-"
                url = f"[Link]({r.url})"
                fresh_marker = " **NEW**" if r.is_fresh_release() else ""
                lines.append(f"| {r.name[:25]}{fresh_marker} | {r.stars} | {r.weight_status} | {conf} | {arxiv} | {url} |")
            lines.append("")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write("\n".join(lines))

        print(f"Exported to {output_path}")

    # RU Queue Management Methods

    def add_to_ru_queue(self, full_name: str) -> bool:
        """Manually add a repo to the RU queue."""
        if full_name not in self.repos:
            print(f"Error: {full_name} not in tracked repos")
            return False

        repo_info = self.repos[full_name]
        if self.ru_queue.add_candidate(repo_info, source="manual"):
            print(f"Added {full_name} to RU queue")
            return True
        else:
            print(f"Could not add {full_name} to RU queue (already exists or no weights)")
            return False

    def remove_from_ru_queue(self, full_name: str) -> bool:
        """Remove a repo from the RU queue."""
        if self.ru_queue.remove_candidate(full_name):
            if full_name in self.repos:
                self.repos[full_name].ru_candidate = False
            print(f"Removed {full_name} from RU queue")
            return True
        else:
            print(f"{full_name} not in RU queue")
            return False

    def list_ru_candidates(self, status: Optional[str] = None) -> List[RUCandidate]:
        """List RU candidates, optionally filtered by status."""
        if status:
            return [c for c in self.ru_queue.list_all() if c.status == status]
        return self.ru_queue.list_all()

    def print_ru_queue(self, status_filter: Optional[str] = None):
        """Print RU queue status."""
        candidates = self.list_ru_candidates(status_filter)

        if not candidates:
            print("RU queue is empty")
            return

        print(f"\nRU Queue ({len(candidates)} candidates)")
        print("-" * 90)
        print(f"{'Repo':<40} {'arXiv':<15} {'Status':<12} {'Source':<8} URL")
        print("-" * 90)

        for c in sorted(candidates, key=lambda x: x.added_at, reverse=True):
            print(f"{c.full_name[:39]:<40} {c.arxiv_id[:14]:<15} {c.status:<12} {c.source:<8} {c.url}")

    def load_issue_repos(self, yaml_path: str) -> List[str]:
        """
        Load repository URLs from the issue-added repos YAML file.

        Args:
            yaml_path: Path to repos_from_issues.yaml

        Returns:
            List of repository URLs
        """
        import yaml

        path = Path(yaml_path)
        if not path.exists():
            return []

        try:
            with open(path, "r") as f:
                data = yaml.safe_load(f)

            if not data or not data.get("repos"):
                return []

            urls = []
            for repo_entry in data["repos"]:
                if isinstance(repo_entry, dict) and "url" in repo_entry:
                    urls.append(repo_entry["url"])
                elif isinstance(repo_entry, str):
                    urls.append(repo_entry)

            return urls

        except Exception as e:
            print(f"Error loading issue repos from {yaml_path}: {e}")
            return []

    def process_issue_repos(self, yaml_path: str) -> int:
        """
        Process repositories added via GitHub Issues.

        This loads repos from the YAML file, fetches their info from GitHub,
        runs them through the detection pipeline, and adds them to tracking.
        After processing, the YAML file is cleared.

        Args:
            yaml_path: Path to repos_from_issues.yaml

        Returns:
            Number of new repos processed
        """
        urls = self.load_issue_repos(yaml_path)
        if not urls:
            return 0

        print(f"Processing {len(urls)} repos from issues...")
        processed = 0

        for url in urls:
            # Extract owner/repo from URL
            # URL format: https://github.com/owner/repo
            try:
                parts = url.rstrip("/").split("/")
                if len(parts) < 2:
                    print(f"  Skipping invalid URL: {url}")
                    continue
                owner = parts[-2]
                repo = parts[-1]
                full_name = f"{owner}/{repo}"
            except Exception:
                print(f"  Skipping invalid URL: {url}")
                continue

            # Check if already tracked
            if full_name in self.repos:
                print(f"  {full_name}: already tracked, skipping")
                continue

            # Fetch repo info from GitHub
            repo_data = self.github.get_repo_details(owner, repo)
            if not repo_data:
                print(f"  {full_name}: could not fetch from GitHub, skipping")
                continue

            # Process through the pipeline (skip relevance filter for user-added repos)
            self._process_issue_repo(repo_data)
            processed += 1
            print(f"  {full_name}: added to tracking")

        # Clear the YAML file after processing
        if processed > 0 or urls:
            self._clear_issue_repos(yaml_path)

        return processed

    def _process_issue_repo(self, repo_data: Dict):
        """
        Process a single repository added via issue.

        This is similar to _process_repo_with_delta but skips the relevance filter
        since the user explicitly requested tracking this repo.
        """
        from .models import RepoInfo

        full_name = repo_data.get("full_name", "")
        if not full_name:
            return

        # Create RepoInfo from GitHub data
        repo_info = RepoInfo.from_github_repo(repo_data)

        # Get README and analyze
        owner, name = full_name.split("/")
        readme = self.github.get_readme(owner, name)
        self._update_repo_detection(repo_info, readme)

        # Store the repo
        self.repos[full_name] = repo_info
        self._new_repos.append(full_name)

    def _clear_issue_repos(self, yaml_path: str):
        """Clear the issue repos YAML file after processing."""
        path = Path(yaml_path)
        try:
            with open(path, "w") as f:
                f.write("# Repositories added via GitHub Issues\n")
                f.write("# These will be processed during the next scheduled update\n")
                f.write("repos: []\n")
            print(f"Cleared issue repos file: {yaml_path}")
        except Exception as e:
            print(f"Error clearing issue repos file: {e}")
