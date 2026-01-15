"""Data models for Paper Tracker."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class RepoState(Enum):
    """Repository state for tracking lifecycle."""
    HAS_WEIGHTS = "has_weights"      # Weights are available
    COMING_SOON = "coming_soon"      # Weights promised but not yet released
    NO_WEIGHTS = "no_weights"        # No weights detected or promised


@dataclass
class RepoInfo:
    """Repository information with detection results."""
    name: str
    full_name: str
    stars: int
    url: str
    description: str
    created_at: str
    updated_at: str

    # State tracking
    status: RepoState = RepoState.NO_WEIGHTS
    last_checked: str = ""  # ISO date
    status_changed_date: str = ""  # ISO date - when status last changed
    previous_status: Optional[RepoState] = None

    # Weight detection
    weight_status: str = "None"
    weight_confidence: str = "none"
    weight_details: List[str] = field(default_factory=list)

    # Conference detection
    conference: Optional[str] = None
    conference_year: Optional[str] = None
    arxiv_id: Optional[str] = None
    conference_details: List[str] = field(default_factory=list)

    # Topics
    topics: List[str] = field(default_factory=list)

    # Coming soon detection
    coming_soon_detected: bool = False
    coming_soon_details: List[str] = field(default_factory=list)

    # RU (Reproducible Unit) candidate status
    ru_candidate: bool = False

    def __post_init__(self):
        """Initialize dates if not set."""
        if not self.last_checked:
            self.last_checked = datetime.now().strftime("%Y-%m-%d")
        if not self.status_changed_date:
            self.status_changed_date = self.last_checked

    def update_status(self, new_status: RepoState):
        """Update status and track the change."""
        if self.status != new_status:
            self.previous_status = self.status
            self.status = new_status
            self.status_changed_date = datetime.now().strftime("%Y-%m-%d")
        self.last_checked = datetime.now().strftime("%Y-%m-%d")

    def is_fresh_release(self, days: int = 7) -> bool:
        """Check if this is a fresh release (status changed to HAS_WEIGHTS recently)."""
        if self.status != RepoState.HAS_WEIGHTS:
            return False
        if self.previous_status is None:
            return False

        try:
            changed_date = datetime.strptime(self.status_changed_date, "%Y-%m-%d")
            days_since = (datetime.now() - changed_date).days
            return days_since <= days
        except (ValueError, TypeError):
            return False

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "full_name": self.full_name,
            "stars": self.stars,
            "url": self.url,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status.value,
            "last_checked": self.last_checked,
            "status_changed_date": self.status_changed_date,
            "previous_status": self.previous_status.value if self.previous_status else None,
            "weight_status": self.weight_status,
            "weight_confidence": self.weight_confidence,
            "weight_details": self.weight_details,
            "conference": self.conference,
            "conference_year": self.conference_year,
            "arxiv_id": self.arxiv_id,
            "conference_details": self.conference_details,
            "topics": self.topics,
            "coming_soon_detected": self.coming_soon_detected,
            "coming_soon_details": self.coming_soon_details,
            "ru_candidate": self.ru_candidate,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RepoInfo":
        """Create from dictionary (JSON deserialization)."""
        # Handle status enum
        status_str = data.get("status", "no_weights")
        status = RepoState(status_str) if status_str else RepoState.NO_WEIGHTS

        # Handle previous_status enum
        prev_status_str = data.get("previous_status")
        previous_status = RepoState(prev_status_str) if prev_status_str else None

        return cls(
            name=data.get("name", ""),
            full_name=data.get("full_name", ""),
            stars=data.get("stars", 0),
            url=data.get("url", ""),
            description=data.get("description", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            status=status,
            last_checked=data.get("last_checked", ""),
            status_changed_date=data.get("status_changed_date", ""),
            previous_status=previous_status,
            weight_status=data.get("weight_status", "None"),
            weight_confidence=data.get("weight_confidence", "none"),
            weight_details=data.get("weight_details", []),
            conference=data.get("conference"),
            conference_year=data.get("conference_year"),
            arxiv_id=data.get("arxiv_id"),
            conference_details=data.get("conference_details", []),
            topics=data.get("topics", []),
            coming_soon_detected=data.get("coming_soon_detected", False),
            coming_soon_details=data.get("coming_soon_details", []),
            ru_candidate=data.get("ru_candidate", False),
        )

    @classmethod
    def from_github_repo(cls, repo: dict) -> "RepoInfo":
        """Create from GitHub API response."""
        return cls(
            name=repo.get("name", ""),
            full_name=repo.get("full_name", ""),
            stars=repo.get("stargazers_count", 0),
            url=repo.get("html_url", ""),
            description=(repo.get("description") or "")[:150],
            created_at=repo.get("created_at", "")[:10],
            updated_at=repo.get("updated_at", "")[:10],
            topics=repo.get("topics", []),
        )


@dataclass
class AwesomeEntry:
    """Entry parsed from an awesome list markdown table."""
    # Core identity
    id: str  # Unique ID: "{source}:{model_name}"
    source_list: str  # e.g., "ChaofWang/Awesome-Super-Resolution"

    # Paper info
    title: str  # Full paper title
    model_name: str  # Model acronym (e.g., "ESRGAN", "SwinIR")
    authors: List[str] = field(default_factory=list)  # Paper authors

    # Publication info
    conference: Optional[str] = None
    year: Optional[str] = None
    arxiv_id: Optional[str] = None
    paper_url: Optional[str] = None

    # Code info
    github_url: Optional[str] = None
    github_full_name: Optional[str] = None

    # Metadata
    keywords: List[str] = field(default_factory=list)
    section: str = ""  # Section from awesome list (e.g., "2024", "Video SR")
    domain: str = ""  # Domain tag (e.g., "image_restoration", "super_resolution")
    subtopics: List[str] = field(default_factory=list)  # Subtopic tags

    # Tracking
    last_synced: str = ""
    has_repo: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "source_list": self.source_list,
            "title": self.title,
            "model_name": self.model_name,
            "authors": self.authors,
            "conference": self.conference,
            "year": self.year,
            "arxiv_id": self.arxiv_id,
            "paper_url": self.paper_url,
            "github_url": self.github_url,
            "github_full_name": self.github_full_name,
            "keywords": self.keywords,
            "section": self.section,
            "domain": self.domain,
            "subtopics": self.subtopics,
            "last_synced": self.last_synced,
            "has_repo": self.has_repo,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AwesomeEntry":
        """Create from dictionary (JSON deserialization)."""
        return cls(
            id=data.get("id", ""),
            source_list=data.get("source_list", ""),
            title=data.get("title", ""),
            model_name=data.get("model_name", ""),
            authors=data.get("authors", []),
            conference=data.get("conference"),
            year=data.get("year"),
            arxiv_id=data.get("arxiv_id"),
            paper_url=data.get("paper_url"),
            github_url=data.get("github_url"),
            github_full_name=data.get("github_full_name"),
            keywords=data.get("keywords", []),
            section=data.get("section", ""),
            domain=data.get("domain", ""),
            subtopics=data.get("subtopics", []),
            last_synced=data.get("last_synced", ""),
            has_repo=data.get("has_repo", False),
        )

    def to_repo_format(self) -> Optional[dict]:
        """Convert to repo dict format for search results integration."""
        if not self.github_url:
            return None

        return {
            "full_name": self.github_full_name or "",
            "name": self.model_name,
            "url": self.github_url,
            "stars": 0,  # Unknown from awesome list
            "description": self.title[:200] if self.title else "",
            "weight_status": "Curated",
            "conference": self.conference or "",
            "conference_year": self.year or "",
            "arxiv_id": self.arxiv_id or "",
            "source": f"awesome:{self.source_list.split('/')[-1]}",
        }
