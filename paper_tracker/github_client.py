"""GitHub API client with rate limiting."""

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from http.client import IncompleteRead
from typing import Dict, List, Optional

from .config_loader import config


@dataclass
class RateLimitInfo:
    """Rate limit information."""
    limit: int
    remaining: int
    reset_time: datetime
    used: int


class GitHubClient:
    """GitHub API client with proper rate limiting."""

    BASE_URL = "https://api.github.com"

    def __init__(self, token: Optional[str] = None):
        self.token = token or config.get("github.token")
        self.rate_limit = RateLimitInfo(
            limit=60,
            remaining=60,
            reset_time=datetime.now(),
            used=0
        )
        self._request_delay = config.get("search.request_delay", 1.5)
        self._rate_limit_buffer = config.get("search.rate_limit_buffer", 10)

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers."""
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "PaperTracker/1.0"
        }
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        return headers

    def _update_rate_limit(self, response):
        """Update rate limit info from response headers."""
        self.rate_limit.limit = int(response.headers.get("X-RateLimit-Limit", 60))
        self.rate_limit.remaining = int(response.headers.get("X-RateLimit-Remaining", 60))
        reset_timestamp = int(response.headers.get("X-RateLimit-Reset", 0))
        if reset_timestamp:
            self.rate_limit.reset_time = datetime.fromtimestamp(reset_timestamp)
        self.rate_limit.used = self.rate_limit.limit - self.rate_limit.remaining

    def _wait_for_rate_limit(self):
        """Wait if rate limit is low."""
        if self.rate_limit.remaining < self._rate_limit_buffer:
            wait_seconds = (self.rate_limit.reset_time - datetime.now()).total_seconds()
            if wait_seconds > 0:
                print(f"Rate limit low ({self.rate_limit.remaining} remaining). "
                      f"Waiting {wait_seconds:.0f}s until reset...")
                time.sleep(wait_seconds + 1)

    def _request(self, url: str, max_retries: int = 3) -> Optional[Dict]:
        """Make request with rate limiting and retries."""
        self._wait_for_rate_limit()

        headers = self._get_headers()
        req = urllib.request.Request(url, headers=headers)

        for attempt in range(max_retries):
            try:
                with urllib.request.urlopen(req, timeout=60) as response:
                    self._update_rate_limit(response)
                    return json.loads(response.read().decode())

            except urllib.error.HTTPError as e:
                if e.code == 403:
                    # Rate limited - wait and retry
                    reset_header = e.headers.get("X-RateLimit-Reset")
                    if reset_header:
                        reset_time = datetime.fromtimestamp(int(reset_header))
                        wait_seconds = (reset_time - datetime.now()).total_seconds()
                        if wait_seconds > 0 and wait_seconds < 3600:
                            print(f"Rate limited. Waiting {wait_seconds:.0f}s...")
                            time.sleep(wait_seconds + 1)
                            continue

                    # Secondary rate limit (abuse detection)
                    retry_after = e.headers.get("Retry-After")
                    if retry_after:
                        wait_seconds = int(retry_after)
                        print(f"Secondary rate limit. Waiting {wait_seconds}s...")
                        time.sleep(wait_seconds)
                        continue

                    print(f"Rate limit error: {e}")
                    return None

                elif e.code == 404:
                    return None

                elif e.code >= 500:
                    # Server error - retry
                    wait_time = 2 ** attempt
                    print(f"Server error {e.code}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue

                else:
                    print(f"HTTP error {e.code}: {e.reason}")
                    return None

            except urllib.error.URLError as e:
                wait_time = 2 ** attempt
                print(f"Network error: {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue

            except (TimeoutError, OSError) as e:
                wait_time = 2 ** attempt
                print(f"Timeout/connection error: {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue

            except IncompleteRead as e:
                # Handle truncated response - try to use partial data
                if e.partial:
                    try:
                        return json.loads(e.partial.decode())
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        pass
                # Retry on next attempt
                wait_time = 2 ** attempt
                print(f"Incomplete read. Retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue

        return None

    def search_repos(
        self,
        query: str,
        min_stars: int = 10,
        per_page: int = 30,
        page: int = 1,
        sort: str = ""
    ) -> tuple[List[Dict], int]:
        """Search GitHub repositories with pagination.

        Args:
            query: Search query
            min_stars: Minimum stars filter
            per_page: Results per page (max 100)
            page: Page number (1-indexed)
            sort: Sort order - "" (relevance/best match), "stars", or "updated"

        Returns:
            Tuple of (items list, total_count)
        """
        # Don't auto-wrap in quotes - let GitHub match all words naturally
        # User can manually add quotes if they want exact phrase matching
        full_query = f"{query} in:name,description,readme stars:>={min_stars}"
        encoded_query = urllib.parse.quote(full_query)

        # Build URL with pagination
        url = f"{self.BASE_URL}/search/repositories?q={encoded_query}&per_page={min(per_page, 100)}&page={page}"
        if sort:
            url += f"&sort={sort}&order=desc"

        result = self._request(url)
        time.sleep(self._request_delay)

        if result:
            return result.get("items", []), result.get("total_count", 0)
        return [], 0

    def get_readme(self, owner: str, repo: str) -> str:
        """Fetch README content from a repository."""
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/readme"
        result = self._request(url)
        time.sleep(self._request_delay)

        if not result:
            return ""

        content = result.get("content", "")
        if content:
            try:
                return base64.b64decode(content).decode("utf-8", errors="ignore")
            except Exception:
                return ""
        return ""

    def get_repo_details(self, owner: str, repo: str) -> Optional[Dict]:
        """Get detailed repository information."""
        url = f"{self.BASE_URL}/repos/{owner}/{repo}"
        result = self._request(url)
        time.sleep(self._request_delay)
        return result

    def get_rate_limit_status(self) -> RateLimitInfo:
        """Get current rate limit status."""
        url = f"{self.BASE_URL}/rate_limit"
        result = self._request(url)
        if result:
            core = result.get("resources", {}).get("core", {})
            self.rate_limit.limit = core.get("limit", 60)
            self.rate_limit.remaining = core.get("remaining", 60)
            reset_timestamp = core.get("reset", 0)
            if reset_timestamp:
                self.rate_limit.reset_time = datetime.fromtimestamp(reset_timestamp)
        return self.rate_limit

    def verify_token(self) -> dict:
        """Verify token and return status info.

        Returns:
            Dict with: valid, authenticated, limit, remaining, reset_time
        """
        info = self.get_rate_limit_status()
        is_authenticated = info.limit > 60  # 60 is unauthenticated limit

        return {
            "valid": info.remaining >= 0,
            "authenticated": is_authenticated,
            "limit": info.limit,
            "remaining": info.remaining,
            "reset_time": info.reset_time.isoformat() if info.reset_time else None,
        }
