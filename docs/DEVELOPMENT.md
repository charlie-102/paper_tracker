# Development Guide

This guide covers how to run, configure, and extend the Paper Implementation Tracker.

## Quick Start

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Setup Environment (Optional)

```bash
cp .env.example .env
# Edit .env and add your GITHUB_TOKEN for higher rate limits
```

### Run Tests

```bash
python -m pytest tests/ -v
# or
python tests/test_pipeline.py
```

### Basic Usage

```bash
# Stateless (fresh search each time)
python -m paper_tracker

# Stateful (recommended - tracks changes)
python -m paper_tracker --history data/history.json --md results/latest.md
```

## CLI Options

| Option | Short | Description |
|--------|-------|-------------|
| `--history` | | Path to history.json for stateful tracking |
| `--token` | `-t` | GitHub personal access token |
| `--config` | `-c` | Path to config.yaml |
| `--min-stars` | `-s` | Minimum stars filter |
| `--max-results` | `-n` | Max results per query per pass |
| `--year` | `-y` | Filter repos created after year |
| `--details` | `-d` | Show detection details |
| `--output` | `-o` | Export to JSON file |
| `--csv` | | Export to CSV file |
| `--md` | | Export to Markdown file |
| `--quiet` | `-q` | Suppress progress output |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `GITHUB_TOKEN` | GitHub personal access token (5000 req/hr vs 60/hr) |
| `TRACKER_MIN_STARS` | Override minimum stars filter |
| `TRACKER_YEAR` | Override year filter |

## How It Works

### Repository States

| State | Description |
|-------|-------------|
| `HAS_WEIGHTS` | Weights are available for download |
| `COMING_SOON` | Weights promised but not yet released (watchlist) |
| `NO_WEIGHTS` | No weights detected or promised |

### Two-Pass Search Strategy

For each query, runs two searches:
1. **Sort by stars**: Catches famous/SOTA repos
2. **Sort by updated**: Catches bleeding-edge/new repos

### Delta Check Logic

| Case | Condition | Action |
|------|-----------|--------|
| **A (Stable)** | In history with `HAS_WEIGHTS` | Skip (update last_checked only) |
| **B (Watchlist)** | In history with `COMING_SOON` | Re-check README for weights |
| **C (New)** | Not in history | Full scan |

### Fresh Release Detection

A repo is marked as **Fresh Release** when:
1. Status is `HAS_WEIGHTS`
2. Status changed from `COMING_SOON` or `NO_WEIGHTS`
3. Change happened within the last 7 days

## Python API

```python
from paper_tracker.tracker import PaperTracker
from paper_tracker.models import RepoState

# Initialize
tracker = PaperTracker(token="your_github_token")

# Load existing state
tracker.load_history("data/history.json")

# Search with delta logic
repos = tracker.search(min_stars=50, year_filter="2024")

# Get fresh releases
fresh = [r for r in repos if r.is_fresh_release(days=7)]

# Get watchlist
watchlist = [r for r in repos if r.status == RepoState.COMING_SOON]

# Save state
tracker.save_history("data/history.json")

# Export
tracker.export_markdown("results/latest.md")
```

## Configuration

Edit `paper_tracker/config.yaml` to customize:

- Search queries
- Relevance keywords (strong/weak)
- Exclude keywords (audio, NLP, etc.)
- Weight detection patterns
- Conference patterns

## Adding New Detection Patterns

### Weight Detection

Add patterns to `config.yaml` under the `weights` section:

```yaml
weights:
  huggingface:
    - "huggingface.co"
    - "hf.co"
  releases:
    - "github.com/.*/releases"
  cloud:
    - "drive.google.com"
    - "dropbox.com"
```

### Conference Detection

Add patterns under the `conferences` section:

```yaml
conferences:
  - pattern: "CVPR\\s*20\\d{2}"
    name: "CVPR"
  - pattern: "NeurIPS\\s*20\\d{2}"
    name: "NeurIPS"
```

## Project Structure

```
paper_tracker/
├── .github/
│   └── workflows/
│       └── main.yml              # GitHub Actions workflow
├── paper_tracker/                # Python package
│   ├── __init__.py
│   ├── __main__.py               # CLI entry point
│   ├── config.yaml               # Configuration
│   ├── config_loader.py          # Config management
│   ├── detectors.py              # Weight, Conference, ComingSoon detection
│   ├── github_client.py          # GitHub API with rate limiting
│   ├── models.py                 # RepoInfo, RepoState
│   └── tracker.py                # Main stateful tracker
├── tests/
│   └── test_pipeline.py          # Tests
├── data/
│   └── history.json              # Persistent state (auto-created)
├── results/
│   ├── latest.md                 # Latest markdown report
│   ├── latest.json               # Latest JSON data
│   └── tracker_YYYYMMDD.*        # Dated snapshots
├── docs/
│   └── DEVELOPMENT.md            # This file
├── .env.example                  # Environment template
├── .gitignore
├── README.md
└── requirements.txt
```

## GitHub Actions

### Setup

1. Push this repo to GitHub
2. Enable Actions in repo settings
3. (Optional) The default `GITHUB_TOKEN` works, or add a PAT for higher limits

### What the Workflow Does

1. Loads `data/history.json` (if exists)
2. Runs two-pass search with delta logic
3. Saves updated `data/history.json`
4. Exports results to `results/`
5. Commits state changes with `[skip ci]`
6. Creates GitHub Issue for fresh releases

### Manual Trigger

Go to **Actions** > **Weekly Paper Tracker** > **Run workflow**

You can customize:
- `min_stars`: Minimum stars filter (default: 20)
- `year`: Year filter for repos created after (default: 2024)

## Rate Limits

| Auth | Limit |
|------|-------|
| Without token | 60 requests/hour |
| With token | 5000 requests/hour |

The tracker waits automatically when rate limit is low.

## License

MIT
