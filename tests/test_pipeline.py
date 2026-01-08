#!/usr/bin/env python3
"""Quick test to verify Paper Tracker pipeline works."""

import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path


def test_imports():
    """Test all modules can be imported."""
    print("Testing imports...")
    from paper_tracker.config_loader import config
    from paper_tracker.github_client import GitHubClient
    from paper_tracker.detectors import WeightDetector, ConferenceDetector, ComingSoonDetector, RelevanceFilter
    from paper_tracker.models import RepoInfo, RepoState
    from paper_tracker.tracker import PaperTracker
    print("  All imports OK")


def test_config():
    """Test config loading."""
    print("Testing config...")
    from paper_tracker.config_loader import config

    config.load()

    assert config.queries, "Queries should not be empty"
    assert config.get("search.min_stars") is not None, "min_stars should be set"
    assert config.relevance.get("strong_keywords"), "strong_keywords should not be empty"
    assert config.weight_detection.get("huggingface"), "HF patterns should exist"
    assert config.conferences.get("patterns"), "Conference patterns should exist"

    print(f"  Loaded {len(config.queries)} queries")
    print(f"  {len(config.relevance.get('strong_keywords', []))} strong keywords")
    print(f"  {len(config.conferences.get('patterns', {}))} conference patterns")
    print("  Config OK")


def test_repo_state():
    """Test RepoState enum and state tracking."""
    print("Testing RepoState...")
    from paper_tracker.models import RepoInfo, RepoState

    # Test enum values
    assert RepoState.HAS_WEIGHTS.value == "has_weights"
    assert RepoState.COMING_SOON.value == "coming_soon"
    assert RepoState.NO_WEIGHTS.value == "no_weights"

    # Test state transitions
    repo = RepoInfo(
        name="test-repo",
        full_name="user/test-repo",
        stars=100,
        url="https://github.com/user/test-repo",
        description="Test",
        created_at="2024-01-01",
        updated_at="2024-06-01",
    )

    assert repo.status == RepoState.NO_WEIGHTS, "Initial status should be NO_WEIGHTS"

    # Simulate status change
    repo.update_status(RepoState.COMING_SOON)
    assert repo.status == RepoState.COMING_SOON
    assert repo.previous_status == RepoState.NO_WEIGHTS

    repo.update_status(RepoState.HAS_WEIGHTS)
    assert repo.status == RepoState.HAS_WEIGHTS
    assert repo.previous_status == RepoState.COMING_SOON
    assert repo.is_fresh_release(days=7)  # Should be fresh (just changed)

    print("  RepoState OK")


def test_detectors():
    """Test detection logic."""
    print("Testing detectors...")
    from paper_tracker.detectors import WeightDetector, ConferenceDetector, ComingSoonDetector, RelevanceFilter

    # Weight detection
    wd = WeightDetector()

    # Test HuggingFace detection
    hf_result = wd.detect("Download from https://huggingface.co/models/test-model")
    assert hf_result.status == "HF", f"Expected HF, got {hf_result.status}"

    # Test release detection
    release_result = wd.detect("Download from https://github.com/user/repo/releases/download/v1.0/model.pth")
    assert release_result.status == "Release", f"Expected Release, got {release_result.status}"

    # Test cloud detection
    cloud_result = wd.detect("Download from https://drive.google.com/file/d/abc123")
    assert cloud_result.status == "Cloud", f"Expected Cloud, got {cloud_result.status}"

    # Test extension detection
    ext_result = wd.detect("Download the pretrained model checkpoint model_x4.pth")
    assert ext_result.status == "Extension", f"Expected Extension, got {ext_result.status}"

    print("  Weight detector OK")

    # Coming soon detection
    csd = ComingSoonDetector()

    # Test various promise patterns
    soon_result = csd.detect("Code will be released soon. Stay tuned!")
    assert soon_result.detected, "Should detect 'will be released'"

    soon_result2 = csd.detect("## TODO\n- [ ] Release pretrained model\n- [x] Upload code")
    assert soon_result2.detected, "Should detect unchecked checkbox"

    soon_result3 = csd.detect("Weights: TBD")
    assert soon_result3.detected, "Should detect TBD"

    soon_result4 = csd.detect("Model coming soon!")
    assert soon_result4.detected, "Should detect coming soon"

    no_soon = csd.detect("Download pretrained weights from the link below.")
    assert not no_soon.detected, "Should not detect false positives"

    print("  Coming soon detector OK")

    # Conference detection
    cd = ConferenceDetector()

    cvpr_result = cd.detect("Accepted to CVPR 2024")
    assert cvpr_result.conference == "CVPR", f"Expected CVPR, got {cvpr_result.conference}"
    assert cvpr_result.year == "2024", f"Expected 2024, got {cvpr_result.year}"

    arxiv_result = cd.detect("Paper: https://arxiv.org/abs/2401.12345")
    assert arxiv_result.arxiv_id == "2401.12345", f"Expected 2401.12345, got {arxiv_result.arxiv_id}"

    print("  Conference detector OK")

    # Relevance filter
    rf = RelevanceFilter()

    relevant_repo = {"name": "super-resolution-net", "description": "Image super resolution", "topics": []}
    assert rf.is_relevant(relevant_repo), "Should be relevant"

    irrelevant_repo = {"name": "audio-denoiser", "description": "Audio denoising tool", "topics": []}
    assert not rf.is_relevant(irrelevant_repo), "Should not be relevant (audio)"

    excluded_repo = {"name": "awesome-super-resolution", "description": "A list of SR papers", "topics": []}
    assert rf.is_excluded(excluded_repo), "Should be excluded (awesome list)"

    print("  Relevance filter OK")


def test_models():
    """Test data models and serialization."""
    print("Testing models...")
    from paper_tracker.models import RepoInfo, RepoState

    repo = RepoInfo(
        name="test-repo",
        full_name="user/test-repo",
        stars=100,
        url="https://github.com/user/test-repo",
        description="Test description",
        created_at="2024-01-01",
        updated_at="2024-06-01",
    )

    repo.weight_status = "HF"
    repo.conference = "CVPR"
    repo.update_status(RepoState.HAS_WEIGHTS)

    # Test serialization
    data = repo.to_dict()
    assert data["name"] == "test-repo"
    assert data["weight_status"] == "HF"
    assert data["conference"] == "CVPR"
    assert data["status"] == "has_weights"

    # Test deserialization
    repo2 = RepoInfo.from_dict(data)
    assert repo2.name == repo.name
    assert repo2.status == repo.status
    assert repo2.weight_status == repo.weight_status

    print("  Models OK")


def test_persistence():
    """Test history loading and saving."""
    print("Testing persistence...")
    from paper_tracker.tracker import PaperTracker
    from paper_tracker.models import RepoInfo, RepoState

    tracker = PaperTracker()

    # Add a test repo
    repo = RepoInfo(
        name="test-repo",
        full_name="user/test-repo",
        stars=100,
        url="https://github.com/user/test-repo",
        description="Test",
        created_at="2024-01-01",
        updated_at="2024-06-01",
    )
    repo.update_status(RepoState.COMING_SOON)
    tracker.repos["user/test-repo"] = repo

    # Save to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_path = f.name

    tracker.save_history(temp_path)

    # Load in new tracker
    tracker2 = PaperTracker()
    loaded = tracker2.load_history(temp_path)

    assert loaded, "Should load history"
    assert "user/test-repo" in tracker2.repos, "Should have test repo"
    assert tracker2.repos["user/test-repo"].status == RepoState.COMING_SOON

    # Cleanup
    Path(temp_path).unlink()

    print("  Persistence OK")


def test_tracker_init():
    """Test tracker initialization."""
    print("Testing tracker initialization...")
    from paper_tracker.tracker import PaperTracker

    tracker = PaperTracker()

    assert tracker.github is not None, "GitHub client should be initialized"
    assert tracker.weight_detector is not None, "Weight detector should be initialized"
    assert tracker.conference_detector is not None, "Conference detector should be initialized"
    assert tracker.coming_soon_detector is not None, "Coming soon detector should be initialized"
    assert tracker.relevance_filter is not None, "Relevance filter should be initialized"

    print(f"  Rate limit: {tracker.github.rate_limit.remaining}/{tracker.github.rate_limit.limit}")
    print("  Tracker init OK")


def test_github_client():
    """Test GitHub client (no actual API calls)."""
    print("Testing GitHub client...")
    from paper_tracker.github_client import GitHubClient

    client = GitHubClient()

    assert client.BASE_URL == "https://api.github.com"
    assert client._request_delay > 0, "Request delay should be positive"
    assert client._rate_limit_buffer > 0, "Rate limit buffer should be positive"

    headers = client._get_headers()
    assert "User-Agent" in headers
    assert "Accept" in headers

    print("  GitHub client OK")


def test_fresh_release_detection():
    """Test fresh release detection logic."""
    print("Testing fresh release detection...")
    from paper_tracker.models import RepoInfo, RepoState
    from datetime import datetime, timedelta

    repo = RepoInfo(
        name="test-repo",
        full_name="user/test-repo",
        stars=100,
        url="https://github.com/user/test-repo",
        description="Test",
        created_at="2024-01-01",
        updated_at="2024-06-01",
    )

    # Simulate lifecycle: NO_WEIGHTS -> COMING_SOON -> HAS_WEIGHTS
    repo.update_status(RepoState.COMING_SOON)
    assert not repo.is_fresh_release(), "COMING_SOON is not a fresh release"

    repo.update_status(RepoState.HAS_WEIGHTS)
    assert repo.is_fresh_release(days=7), "Just changed to HAS_WEIGHTS should be fresh"

    # Simulate old release (manually set old date)
    repo.status_changed_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
    assert not repo.is_fresh_release(days=7), "10-day old release is not fresh"

    print("  Fresh release detection OK")


def run_all_tests():
    """Run all tests."""
    print("=" * 50)
    print("Paper Tracker Pipeline Tests (Stateful)")
    print("=" * 50)
    print()

    tests = [
        test_imports,
        test_config,
        test_repo_state,
        test_detectors,
        test_models,
        test_persistence,
        test_tracker_init,
        test_github_client,
        test_fresh_release_detection,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  FAILED: {e}")
            failed += 1
        print()

    print("=" * 50)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 50)

    return failed == 0


if __name__ == "__main__":
    # Add parent directory to path for imports
    sys.path.insert(0, str(Path(__file__).parent.parent))

    success = run_all_tests()
    sys.exit(0 if success else 1)
