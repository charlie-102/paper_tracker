"""
GitHub search module for Model Shop web UI.

Provides stateless search functionality that can be used independently
from the main PaperTracker for web UI searches.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from .github_client import GitHubClient
from .detectors import WeightDetector, ConferenceDetector


# Search templates for quick preset searches
SEARCH_TEMPLATES = {
    "CVPR'24 Vision": {
        "keywords": "image restoration, super resolution, image enhancement",
        "conferences": ["CVPR"],
        "year": "2024",
        "weights": "Has Weights"
    },
    "ECCV'24 Restoration": {
        "keywords": "image denoising, deblurring, inpainting",
        "conferences": ["ECCV"],
        "year": "2024",
        "weights": "Has Weights"
    },
    "Medical Imaging": {
        "keywords": "CT denoising, MRI reconstruction, medical image",
        "conferences": ["MICCAI", "ISBI", "MIDL"],
        "year": "Any",
        "weights": "Has Weights"
    },
    "Video Processing": {
        "keywords": "video restoration, frame interpolation, video denoising",
        "conferences": [],
        "year": "2024",
        "weights": "Has Weights"
    },
    "Low-Light Enhancement": {
        "keywords": "low-light enhancement, low light image, night image",
        "conferences": [],
        "year": "2024",
        "weights": "Has Weights"
    }
}

# Default path for search results
SEARCH_RESULTS_PATH = Path(__file__).parent.parent / "data" / "search_results.json"


def build_search_query(keyword: str, conferences: list, year: str) -> str:
    """Build optimized GitHub search query with conference and year.

    Example: "image restoration CVPR 2024" or "denoising NeurIPS"
    """
    parts = [keyword]
    if conferences:
        parts.append(" ".join(conferences))
    if year and year != "Any":
        parts.append(year)
    return " ".join(parts)


class GitHubSearcher:
    """Stateless GitHub search for web UI.

    Searches GitHub for ML repos with pretrained weights,
    without maintaining any history state.
    """

    def __init__(self, token: Optional[str] = None):
        """Initialize searcher with optional GitHub token.

        Args:
            token: GitHub personal access token for higher rate limits.
                   If not provided, uses GITHUB_TOKEN env var.
        """
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.github = GitHubClient(self.token)
        self.weight_detector = WeightDetector()
        self.conference_detector = ConferenceDetector()

    def search_fast(
        self,
        keywords: list[str],
        conferences: list[str] = None,
        year: str = None,
        min_stars: int = 10,
        max_results_per_keyword: int = 100,
    ) -> list[dict]:
        """Fast search - returns GitHub metadata only, no README/weight detection.

        Fetches all results for all keywords, combines and deduplicates them,
        then sorts by stars (descending) for relevance. UI handles pagination.

        Args:
            keywords: List of search terms
            conferences: Conference names to include in query (e.g., ["CVPR", "ECCV"])
            year: Year to include in query (e.g., "2024")
            min_stars: Minimum stars filter
            max_results_per_keyword: Max results to fetch per keyword from GitHub API

        Returns:
            List of repo dicts (combined, deduplicated, sorted by stars)
        """
        conferences = conferences or []
        results = []
        seen = set()

        for keyword in keywords:
            keyword = keyword.strip()
            if not keyword:
                continue

            # Build optimized query with conference and year
            query = build_search_query(keyword, conferences, year)

            repos, _ = self.github.search_repos(
                query=query,
                min_stars=min_stars,
                per_page=max_results_per_keyword,
                page=1,
                sort=""
            )

            for repo in repos:
                full_name = repo.get("full_name", "")
                if not full_name or full_name in seen:
                    continue
                seen.add(full_name)

                results.append({
                    "full_name": full_name,
                    "name": repo.get("name", ""),
                    "url": repo.get("html_url", f"https://github.com/{full_name}"),
                    "stars": repo.get("stargazers_count", 0),
                    "description": (repo.get("description") or "")[:200],
                    "weight_status": "Unknown",  # Not checked yet
                    "created_at": (repo.get("created_at") or "")[:10],
                    "updated_at": (repo.get("updated_at") or "")[:10],
                })

        # Sort by stars descending for relevance
        results.sort(key=lambda x: x.get("stars", 0), reverse=True)
        return results

    def detect_weights_for_repo(self, full_name: str) -> dict:
        """Detect weights for a single repo by fetching its README.

        Args:
            full_name: Repo full name (e.g., "owner/repo")

        Returns:
            Dict with weight_status and weight_details
        """
        owner, name = full_name.split("/")
        readme = self.github.get_readme(owner, name)
        weight_result = self.weight_detector.detect(readme)

        return {
            "weight_status": weight_result.status if weight_result.status != "None" else "None",
            "weight_details": weight_result.details[:3] if weight_result.details else [],
        }

    def search(
        self,
        keywords: list[str],
        conferences: list[str] = None,
        conference_year: str = None,
        weight_filter: str = "has_weights",
        min_stars: int = 10,
        max_results_per_keyword: int = 30,
    ) -> list[dict]:
        """Search GitHub for repos matching criteria.

        Args:
            keywords: List of search terms (e.g., ["image restoration", "super resolution"])
            conferences: Filter by conference (e.g., ["CVPR", "ECCV"]). Empty/None = all.
            conference_year: Filter by year (e.g., "2024"). "Any" or None = all years.
            weight_filter: "has_weights", "no_weights", or "all"
            min_stars: Minimum stars to include
            max_results_per_keyword: Max results per keyword search

        Returns:
            List of repo dicts with detection results
        """
        conferences = conferences or []
        if conference_year == "Any":
            conference_year = None

        seen_repos = set()
        results = []

        for keyword in keywords:
            keyword = keyword.strip()
            if not keyword:
                continue

            # Search GitHub
            repos = self.github.search_repos(
                query=keyword,
                min_stars=min_stars,
                max_results=max_results_per_keyword,
                sort=""
            )

            for repo_data in repos:
                full_name = repo_data.get("full_name", "")
                if not full_name or full_name in seen_repos:
                    continue
                seen_repos.add(full_name)

                # Get README and run detection
                owner, name = full_name.split("/")
                readme = self.github.get_readme(owner, name)

                # Detect weights
                weight_result = self.weight_detector.detect(readme)
                has_weights = weight_result.status != "None"

                # Apply weight filter
                if weight_filter == "has_weights" and not has_weights:
                    continue
                if weight_filter == "no_weights" and has_weights:
                    continue

                # Detect conference
                description = repo_data.get("description", "") or ""
                conf_result = self.conference_detector.detect(readme, description)

                # Apply conference filter
                if conferences:
                    if not conf_result.conference or conf_result.conference not in conferences:
                        continue

                # Apply year filter
                if conference_year:
                    if not conf_result.year or conf_result.year != conference_year:
                        continue

                # Build result dict
                result = {
                    "full_name": full_name,
                    "name": repo_data.get("name", name),
                    "url": repo_data.get("html_url", f"https://github.com/{full_name}"),
                    "stars": repo_data.get("stargazers_count", 0),
                    "description": description[:200] if description else "",
                    "weight_status": weight_result.status if has_weights else "None",
                    "weight_details": weight_result.details[:3] if weight_result.details else [],
                    "conference": conf_result.conference or "",
                    "conference_year": conf_result.year or "",
                    "arxiv_id": conf_result.arxiv_id or "",
                    "created_at": repo_data.get("created_at", "")[:10],
                    "updated_at": repo_data.get("updated_at", "")[:10],
                }
                results.append(result)

        # Keep GitHub's relevance order
        return results

    def search_iter(
        self,
        keywords: list[str],
        conferences: list[str] = None,
        conference_year: str = None,
        weight_filter: str = "has_weights",
        min_stars: int = 10,
        max_results_per_keyword: int = 30,
    ):
        """Generator that yields repos one at a time as they're processed.

        Args:
            Same as search()

        Yields:
            Tuple of (repo_dict or None, processed_count, total_count, status_msg)
            - repo_dict is None during "fetching" phase, contains repo during "processing" phase
        """
        conferences = conferences or []
        if conference_year == "Any":
            conference_year = None

        # Phase 1: Gather all repo data from API (fast)
        all_repos = []
        seen_repos = set()
        keywords_clean = [k.strip() for k in keywords if k.strip()]

        for kw_idx, keyword in enumerate(keywords_clean):
            yield None, kw_idx, len(keywords_clean), f"Fetching repos for '{keyword}'..."

            repos = self.github.search_repos(
                query=keyword,
                min_stars=min_stars,
                max_results=max_results_per_keyword,
                sort=""
            )

            for repo_data in repos:
                full_name = repo_data.get("full_name", "")
                if full_name and full_name not in seen_repos:
                    seen_repos.add(full_name)
                    all_repos.append(repo_data)

        total = len(all_repos)
        if total == 0:
            return

        # Phase 2: Process each repo (slow - fetches README)
        for idx, repo_data in enumerate(all_repos):
            full_name = repo_data.get("full_name", "")
            owner, name = full_name.split("/")

            # Get README and run detection
            readme = self.github.get_readme(owner, name)

            # Detect weights
            weight_result = self.weight_detector.detect(readme)
            has_weights = weight_result.status != "None"

            # Apply weight filter
            if weight_filter == "has_weights" and not has_weights:
                yield None, idx + 1, total, f"Processing {idx + 1}/{total}..."
                continue
            if weight_filter == "no_weights" and has_weights:
                yield None, idx + 1, total, f"Processing {idx + 1}/{total}..."
                continue

            # Detect conference
            description = repo_data.get("description", "") or ""
            conf_result = self.conference_detector.detect(readme, description)

            # Apply conference filter
            if conferences:
                if not conf_result.conference or conf_result.conference not in conferences:
                    yield None, idx + 1, total, f"Processing {idx + 1}/{total}..."
                    continue

            # Apply year filter
            if conference_year:
                if not conf_result.year or conf_result.year != conference_year:
                    yield None, idx + 1, total, f"Processing {idx + 1}/{total}..."
                    continue

            # Build result dict
            result = {
                "full_name": full_name,
                "name": repo_data.get("name", name),
                "url": repo_data.get("html_url", f"https://github.com/{full_name}"),
                "stars": repo_data.get("stargazers_count", 0),
                "description": description[:200] if description else "",
                "weight_status": weight_result.status if has_weights else "None",
                "weight_details": weight_result.details[:3] if weight_result.details else [],
                "conference": conf_result.conference or "",
                "conference_year": conf_result.year or "",
                "arxiv_id": conf_result.arxiv_id or "",
                "created_at": repo_data.get("created_at", "")[:10],
                "updated_at": repo_data.get("updated_at", "")[:10],
            }
            yield result, idx + 1, total, f"Processing {idx + 1}/{total}..."

    def search_single_query(
        self,
        query: str,
        min_stars: int = 10,
        max_results: int = 50,
    ) -> list[dict]:
        """Simple search with a single query string.

        Args:
            query: Search query (can include conference/year)
            min_stars: Minimum stars
            max_results: Maximum results

        Returns:
            List of repo dicts
        """
        return self.search(
            keywords=[query],
            conferences=[],
            conference_year=None,
            weight_filter="all",
            min_stars=min_stars,
            max_results_per_keyword=max_results,
        )


def save_search_results(
    repos: list[dict],
    query_info: dict = None,
    output_path: str = None
) -> str:
    """Save search results to JSON file.

    Args:
        repos: List of repo dicts from search
        query_info: Optional dict with query parameters used
        output_path: Output file path (default: data/search_results.json)

    Returns:
        Path to saved file
    """
    output_path = Path(output_path or SEARCH_RESULTS_PATH)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "last_search": datetime.now().isoformat(),
        "query": query_info or {},
        "count": len(repos),
        "repos": repos
    }

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    return str(output_path)


def load_search_results(input_path: str = None) -> tuple[list[dict], dict]:
    """Load search results from JSON file.

    Args:
        input_path: Input file path (default: data/search_results.json)

    Returns:
        Tuple of (repos list, metadata dict)
    """
    input_path = Path(input_path or SEARCH_RESULTS_PATH)

    if not input_path.exists():
        return [], {"last_search": None, "query": {}, "count": 0}

    with open(input_path, "r") as f:
        data = json.load(f)

    repos = data.get("repos", [])
    metadata = {
        "last_search": data.get("last_search"),
        "query": data.get("query", {}),
        "count": data.get("count", len(repos))
    }

    return repos, metadata


def append_to_search_results(
    new_repos: list[dict],
    input_path: str = None
) -> int:
    """Append new repos to existing search results (avoiding duplicates).

    Args:
        new_repos: New repos to add
        input_path: File path (default: data/search_results.json)

    Returns:
        Number of repos added
    """
    repos, metadata = load_search_results(input_path)

    existing_names = {r["full_name"] for r in repos}
    added = 0

    for repo in new_repos:
        if repo["full_name"] not in existing_names:
            repos.append(repo)
            existing_names.add(repo["full_name"])
            added += 1

    if added > 0:
        save_search_results(repos, metadata.get("query"), input_path)

    return added
