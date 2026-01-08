"""Main tracker module with stateful tracking."""

import json
import csv
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set

from .config_loader import config
from .github_client import GitHubClient
from .detectors import WeightDetector, ConferenceDetector, ComingSoonDetector, RelevanceFilter
from .models import RepoInfo, RepoState


class PaperTracker:
    """Stateful tracker for finding reproducible ML repos."""

    def __init__(self, token: Optional[str] = None, config_path: Optional[str] = None):
        # Load config
        config.load(config_path)

        # Initialize components
        self.github = GitHubClient(token)
        self.weight_detector = WeightDetector()
        self.conference_detector = ConferenceDetector()
        self.coming_soon_detector = ComingSoonDetector()
        self.relevance_filter = RelevanceFilter()

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
                # Case A: Stable - just update last_checked
                existing.last_checked = datetime.now().strftime("%Y-%m-%d")
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

        return {
            "total": len(repos),
            "with_weights": with_weights,
            "coming_soon": coming_soon,
            "fresh_releases": len(fresh_releases),
            "new_this_run": len(self._new_repos),
            "by_status": status_counts,
            "by_weight_status": weight_counts,
            "by_conference": conf_counts,
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
