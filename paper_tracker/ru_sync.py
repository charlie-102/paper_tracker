"""
RU (Reproducible Unit) synchronization utilities.

Handles detection of existing RU units and matching with paper_tracker results.
"""

import os
import re
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

# Hardcoded path for now
RU_UNITS_PATH = "/Users/long/Downloads/claudegit/RU/zoo/units"

# Path to candidates tracking file
CANDIDATES_FILE = Path(__file__).parent.parent / "data" / "ru_candidates.json"


def normalize_name(name: str) -> str:
    """Normalize a repo name for comparison.

    Handles variations like:
    - MoCE-IR -> moceir
    - Noise-DA -> noiseda
    - ComfyUI-SUPIR -> supir (extracts core name)
    - ASTv2_RU -> astv2
    """
    # Remove common prefixes
    prefixes_to_remove = ["comfyui-", "comfyui_"]
    name_lower = name.lower()
    for prefix in prefixes_to_remove:
        if name_lower.startswith(prefix):
            name_lower = name_lower[len(prefix):]
            break

    # Remove _RU suffix (from RU unit folder names)
    if name_lower.endswith("_ru"):
        name_lower = name_lower[:-3]

    # Remove special characters (-, _, spaces)
    normalized = re.sub(r'[-_\s]', '', name_lower)

    return normalized


def get_existing_ru_units(ru_path: str = RU_UNITS_PATH) -> dict[str, str]:
    """Get list of existing RU units from the zoo/units directory.

    Returns:
        dict mapping normalized name -> original folder name
    """
    ru_units = {}

    if not os.path.exists(ru_path):
        return ru_units

    for item in os.listdir(ru_path):
        item_path = os.path.join(ru_path, item)
        if os.path.isdir(item_path) and not item.startswith('.'):
            normalized = normalize_name(item)
            ru_units[normalized] = item

    return ru_units


def is_in_ru(repo_name: str, ru_units: dict[str, str]) -> bool:
    """Check if a repo name matches any existing RU unit."""
    normalized = normalize_name(repo_name)
    return normalized in ru_units


def load_tracker_results(results_path: Optional[Path] = None) -> list[dict]:
    """Load paper tracker results from JSON file.

    Args:
        results_path: Path to results JSON. Defaults to results/test.json (or latest.json)

    Returns:
        List of repo dictionaries
    """
    if results_path is None:
        results_dir = Path(__file__).parent.parent / "results"
        # Prefer test.json (usually more recent), fallback to latest.json
        test_path = results_dir / "test.json"
        latest_path = results_dir / "latest.json"

        if test_path.exists():
            results_path = test_path
        elif latest_path.exists():
            results_path = latest_path
        else:
            return []

    if not results_path.exists():
        return []

    with open(results_path, 'r') as f:
        data = json.load(f)

    # Handle both list format and dict with "repos" key
    if isinstance(data, list):
        return data
    elif isinstance(data, dict) and "repos" in data:
        return data["repos"]
    elif isinstance(data, dict):
        # Might be keyed by repo name
        return list(data.values())

    return []


def filter_candidates(repos: list[dict], ru_units: dict[str, str]) -> list[dict]:
    """Filter repos to only include candidates (has_weights and not in RU).

    Args:
        repos: List of repo dictionaries from paper tracker
        ru_units: Dict of existing RU units from get_existing_ru_units()

    Returns:
        List of candidate repos
    """
    candidates = []

    for repo in repos:
        # Check if has weights
        status = repo.get("status", "").lower()
        if status != "has_weights":
            continue

        # Check if not already in RU
        name = repo.get("name", "")
        if is_in_ru(name, ru_units):
            continue

        candidates.append(repo)

    return candidates


def load_candidate_status() -> dict:
    """Load candidate status from tracking file."""
    if not CANDIDATES_FILE.exists():
        return {
            "candidates": {},
            "cart": [],
            "last_sync": None
        }

    with open(CANDIDATES_FILE, 'r') as f:
        return json.load(f)


def save_candidate_status(data: dict) -> None:
    """Save candidate status to tracking file."""
    # Ensure data directory exists
    CANDIDATES_FILE.parent.mkdir(parents=True, exist_ok=True)

    data["last_sync"] = datetime.now().isoformat()

    with open(CANDIDATES_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def sync_candidates(repos: list[dict], ru_units: dict[str, str]) -> dict:
    """Sync paper tracker results with candidate tracking.

    Merges new candidates with existing status, preserving user decisions.

    Args:
        repos: List of repo dictionaries from paper tracker
        ru_units: Dict of existing RU units

    Returns:
        Updated candidate status dict
    """
    # Load existing status
    status_data = load_candidate_status()
    existing = status_data.get("candidates", {})

    # Filter to candidates
    new_candidates = filter_candidates(repos, ru_units)

    # Merge - add new ones, keep existing status
    for repo in new_candidates:
        name = repo.get("name", "")
        full_name = repo.get("full_name", name)

        if full_name not in existing:
            existing[full_name] = {
                "url": repo.get("url", f"https://github.com/{full_name}"),
                "name": name,
                "stars": repo.get("stars", 0),
                "conference": repo.get("conference", ""),
                "conference_year": repo.get("conference_year", ""),
                "weight_source": repo.get("weight_status", ""),
                "status": "new",
                "added_at": datetime.now().isoformat(),
                "reviewed_at": None,
                "source": "auto"
            }

    # Remove candidates that are now in RU
    to_remove = []
    for full_name in existing:
        name = existing[full_name].get("name", full_name.split("/")[-1])
        if is_in_ru(name, ru_units):
            to_remove.append(full_name)

    for full_name in to_remove:
        del existing[full_name]
        # Also remove from cart if present
        if full_name in status_data.get("cart", []):
            status_data["cart"].remove(full_name)

    status_data["candidates"] = existing
    return status_data


def export_cart_links(status_data: dict) -> str:
    """Export cart items as GitHub URLs, one per line."""
    cart = status_data.get("cart", [])
    candidates = status_data.get("candidates", {})

    urls = []
    for full_name in cart:
        if full_name in candidates:
            urls.append(candidates[full_name].get("url", f"https://github.com/{full_name}"))

    return "\n".join(urls)


def add_manual_repo(url: str, status_data: dict) -> tuple[bool, str]:
    """Add a manual repo URL to candidates.

    Args:
        url: GitHub repo URL
        status_data: Current status data

    Returns:
        (success, message) tuple
    """
    # Parse URL to get full_name
    match = re.match(r'https?://github\.com/([^/]+/[^/]+)/?', url)
    if not match:
        return False, "Invalid GitHub URL format"

    full_name = match.group(1).rstrip('/')
    name = full_name.split('/')[-1]

    candidates = status_data.get("candidates", {})

    if full_name in candidates:
        return False, f"Repo {name} already in candidates"

    candidates[full_name] = {
        "url": f"https://github.com/{full_name}",
        "name": name,
        "stars": 0,  # Unknown for manual adds
        "conference": "",
        "conference_year": "",
        "weight_source": "manual",
        "status": "new",
        "added_at": datetime.now().isoformat(),
        "reviewed_at": None,
        "source": "manual"
    }

    status_data["candidates"] = candidates
    return True, f"Added {name} to candidates"
