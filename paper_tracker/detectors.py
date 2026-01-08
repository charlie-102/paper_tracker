"""Detection logic for weights, conferences, coming soon, and relevance."""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .config_loader import config


@dataclass
class WeightDetectionResult:
    """Result of weight detection."""
    status: str  # HF, Release, Cloud, Extension, None
    confidence: str  # high, medium, low
    details: List[str] = field(default_factory=list)


@dataclass
class ConferenceDetectionResult:
    """Result of conference detection."""
    conference: Optional[str]
    year: Optional[str]
    arxiv_id: Optional[str]
    details: List[str] = field(default_factory=list)


@dataclass
class ComingSoonResult:
    """Result of coming soon detection."""
    detected: bool
    details: List[str] = field(default_factory=list)


class WeightDetector:
    """Detect pretrained weights in README content."""

    def __init__(self):
        self._load_patterns()

    def _load_patterns(self):
        """Load patterns from config."""
        wd = config.weight_detection

        self.hf_patterns = [re.compile(p, re.IGNORECASE) for p in wd.get("huggingface", [])]
        self.release_patterns = [re.compile(p, re.IGNORECASE) for p in wd.get("github_release", [])]

        self.cloud_patterns = {}
        for drive, patterns in wd.get("cloud_drives", {}).items():
            self.cloud_patterns[drive] = [re.compile(p, re.IGNORECASE) for p in patterns]

        self.model_extensions = wd.get("model_extensions", [])
        self.weight_keywords = wd.get("weight_keywords", [])

    def detect(self, readme_content: str) -> WeightDetectionResult:
        """
        Detect pretrained weights in README.

        Returns WeightDetectionResult with status and details.
        """
        if not readme_content:
            return WeightDetectionResult(status="None", confidence="none")

        readme_lower = readme_content.lower()
        details = []

        # 1. HuggingFace (highest confidence)
        for pattern in self.hf_patterns:
            matches = pattern.findall(readme_content)
            if matches:
                for m in matches[:3]:
                    detail = m[:60] + "..." if len(m) > 60 else m
                    details.append(f"HF: {detail}")

        if details:
            return WeightDetectionResult(status="HF", confidence="high", details=details)

        # 2. GitHub releases (high confidence)
        for pattern in self.release_patterns:
            matches = pattern.findall(readme_content)
            if matches:
                for m in matches[:3]:
                    detail = m[:60] + "..." if len(m) > 60 else m
                    details.append(f"Release: {detail}")

        if details:
            return WeightDetectionResult(status="Release", confidence="high", details=details)

        # 3. Cloud drives (medium confidence)
        for drive_name, patterns in self.cloud_patterns.items():
            for pattern in patterns:
                matches = pattern.findall(readme_content)
                if matches:
                    for m in matches[:2]:
                        detail = m[:50] + "..." if len(m) > 50 else m
                        details.append(f"{drive_name}: {detail}")

        if details:
            return WeightDetectionResult(status="Cloud", confidence="medium", details=details)

        # 4. Model extensions near keywords (lower confidence)
        for ext in self.model_extensions:
            if ext not in readme_lower:
                continue

            ext_positions = [m.start() for m in re.finditer(re.escape(ext), readme_lower)]
            for pos in ext_positions:
                context = readme_lower[max(0, pos - 100):pos + 100]

                for keyword in self.weight_keywords:
                    if keyword in context:
                        snippet = readme_content[max(0, pos - 50):pos + 20]
                        match = re.search(r'[\w\-\.]+' + re.escape(ext), snippet, re.IGNORECASE)
                        if match:
                            details.append(f"File: {match.group()}")
                            break

                if len(details) >= 3:
                    break

            if len(details) >= 3:
                break

        if details:
            return WeightDetectionResult(status="Extension", confidence="low", details=details)

        return WeightDetectionResult(status="None", confidence="none")


class ComingSoonDetector:
    """Detect 'coming soon' promises for weights in README content."""

    # Patterns for detecting weight release promises
    PROMISE_PATTERNS = [
        # Direct promises
        (r'code\s+(?:will\s+be|to\s+be)\s+released', "code will be released"),
        (r'weights?\s+(?:will\s+be|to\s+be)\s+released', "weights will be released"),
        (r'model\s+(?:will\s+be|to\s+be)\s+released', "model will be released"),
        (r'checkpoint\s+(?:will\s+be|to\s+be)\s+released', "checkpoint will be released"),
        (r'pretrained\s+(?:will\s+be|to\s+be)\s+released', "pretrained will be released"),

        # Coming soon variants
        (r'(?:weights?|model|checkpoint|code)\s*(?::|is|are)?\s*coming\s+soon', "coming soon"),
        (r'coming\s+soon\s*(?::|\.|\!)', "coming soon"),
        (r'release\s+(?:coming\s+)?soon', "release soon"),
        (r'stay\s+tuned', "stay tuned"),

        # Unchecked checkboxes near weight-related terms
        (r'\[\s*\]\s*(?:.*?)(?:model|weights?|checkpoint|pretrained)', "unchecked: model/weights"),
        (r'\[\s*\]\s*(?:.*?)(?:release|download)', "unchecked: release/download"),

        # TBD patterns
        (r'(?:weights?|model|checkpoint)\s*(?::|is|are)?\s*TBD', "TBD"),
        (r'TBD\s*(?::|\.|\!)?\s*(?:.*?)(?:weights?|model|checkpoint)', "TBD"),

        # Work in progress
        (r'(?:weights?|model)\s*(?::|is|are)?\s*(?:WIP|work\s+in\s+progress)', "WIP"),

        # Under preparation
        (r'(?:weights?|model|code)\s+(?:under|in)\s+preparation', "under preparation"),
    ]

    def __init__(self):
        self.patterns = [
            (re.compile(pattern, re.IGNORECASE | re.MULTILINE), desc)
            for pattern, desc in self.PROMISE_PATTERNS
        ]

    def detect(self, readme_content: str) -> ComingSoonResult:
        """
        Detect 'coming soon' promises in README.

        Only looks at the first 3000 characters (typically the intro/status section).

        Returns ComingSoonResult with detected flag and details.
        """
        if not readme_content:
            return ComingSoonResult(detected=False)

        # Only check the first 3000 chars (intro section)
        text = readme_content[:3000]
        details = []

        for pattern, description in self.patterns:
            matches = pattern.findall(text)
            if matches:
                # Get the actual matched text
                match = pattern.search(text)
                if match:
                    matched_text = match.group()[:50]
                    details.append(f"{description}: '{matched_text}'")

                if len(details) >= 3:
                    break

        return ComingSoonResult(detected=len(details) > 0, details=details)


class ConferenceDetector:
    """Detect conference publications in README content."""

    def __init__(self):
        self._load_patterns()

    def _load_patterns(self):
        """Load patterns from config."""
        conf = config.conferences

        self.conference_patterns = {}
        for venue, keywords in conf.get("patterns", {}).items():
            patterns = []
            for kw in keywords:
                # Create pattern that matches keyword with optional year
                pattern = re.compile(
                    rf'\b{re.escape(kw)}(?:\s*[\'"]?\s*(\d{{4}}))?',
                    re.IGNORECASE
                )
                patterns.append(pattern)
            self.conference_patterns[venue] = patterns

        arxiv_pattern = conf.get("arxiv_pattern", r'arxiv\.org/abs/(\d{4}\.\d{4,5})')
        self.arxiv_pattern = re.compile(arxiv_pattern, re.IGNORECASE)

    def detect(self, readme_content: str, repo_description: str = "") -> ConferenceDetectionResult:
        """
        Detect conference publication in README.

        Returns ConferenceDetectionResult with venue, year, and arxiv info.
        """
        if not readme_content:
            return ConferenceDetectionResult(conference=None, year=None, arxiv_id=None)

        text = f"{repo_description}\n{readme_content}"
        details = []

        # Detect conference
        detected_conference = None
        detected_year = None

        for venue, patterns in self.conference_patterns.items():
            for pattern in patterns:
                match = pattern.search(text)
                if match:
                    detected_conference = venue
                    # Try to extract year from match groups or nearby text
                    if match.lastindex and match.group(1):
                        detected_year = match.group(1)
                    else:
                        # Look for year in surrounding context
                        year_match = re.search(r'20[2-3]\d', text[max(0, match.start()-20):match.end()+20])
                        if year_match:
                            detected_year = year_match.group()

                    details.append(f"{venue}: {match.group()}")
                    break
            if detected_conference:
                break

        # Detect arXiv
        arxiv_id = None
        arxiv_match = self.arxiv_pattern.search(text)
        if arxiv_match:
            arxiv_id = arxiv_match.group(1)
            details.append(f"arXiv: {arxiv_id}")

        return ConferenceDetectionResult(
            conference=detected_conference,
            year=detected_year,
            arxiv_id=arxiv_id,
            details=details
        )


class RelevanceFilter:
    """Filter repos by relevance to low-level vision tasks."""

    def __init__(self):
        self._load_keywords()

    def _load_keywords(self):
        """Load keywords from config."""
        rel = config.relevance

        self.strong_keywords = [kw.lower() for kw in rel.get("strong_keywords", [])]
        self.weak_keywords = [kw.lower() for kw in rel.get("weak_keywords", [])]
        self.exclude_keywords = [kw.lower() for kw in rel.get("exclude_keywords", [])]
        self.exclude_name_terms = [t.lower() for t in rel.get("exclude_name_terms", [])]

    def is_relevant(self, repo: Dict) -> bool:
        """Check if repo is relevant to low-level vision tasks."""
        name = repo.get("name", "").lower()
        description = (repo.get("description") or "").lower()
        topics = [t.lower() for t in repo.get("topics", [])]

        text = f"{name} {description} {' '.join(topics)}"

        # Check excludes first
        for keyword in self.exclude_keywords:
            if keyword in text:
                return False

        # Check strong keywords
        for keyword in self.strong_keywords:
            if keyword in text:
                return True

        # Check weak keywords with image context
        has_image_context = any(ctx in text for ctx in ["image", "photo", "picture", "visual"])
        if has_image_context:
            for keyword in self.weak_keywords:
                if keyword in text:
                    return True

        return False

    def is_excluded(self, repo: Dict) -> bool:
        """Check if repo should be excluded (lists, surveys, etc.)."""
        name = repo.get("name", "").lower()
        description = (repo.get("description") or "").lower()

        for term in self.exclude_name_terms:
            if term in name:
                return True
            if description.startswith(term) or f"a {term}" in description[:50]:
                return True

        return False
