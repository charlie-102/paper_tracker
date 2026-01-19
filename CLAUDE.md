# Paper Implementation Tracker

## Overview

Automatically tracks GitHub repos for **low-level vision** papers (super-resolution, denoising, restoration, etc.) that have **pretrained weights** available.

## Quick Commands

```bash
# Run tracker (stateful)
python -m paper_tracker --history data/history.json --md results/latest.md

# Start web UI (port 7860)
./run_web_ui.sh

# Run tests
python -m pytest tests/ -v

# Sync awesome lists
python -m paper_tracker --sync-awesome
```

## Architecture

| Module | Purpose |
|--------|---------|
| `tracker.py` | Main stateful tracker with delta logic |
| `web_ui.py` | Gradio web interface (Search + Shop tabs) |
| `detectors.py` | Weight and conference detection |
| `github_search.py` | Stateless search for web UI |
| `awesome_manager.py` | Curated list sync/search |
| `parsers/` | Plugin-based survey table parsers |

## Data Flow

1. GitHub API search (two-pass: stars + updated)
2. Delta check against `data/history.json`
3. Weight/conference detection on README
4. Export to `results/latest.*`

## Key Patterns

- **Repository states**: `HAS_WEIGHTS`, `COMING_SOON`, `NO_WEIGHTS`
- **Fresh release**: Status changed to `HAS_WEIGHTS` within 7 days
- **Config-driven**: Search queries and patterns in `paper_tracker/config.yaml`
- **RU queue**: Repos with weights + arXiv ID auto-queued for Reproducible Unit generation

## Data Files

| File | Purpose |
|------|---------|
| `data/history.json` | Persistent repo tracking state |
| `data/ru_queue.yaml` | Reproducible unit candidates |
| `data/repos_from_issues.yaml` | Repos added via GitHub Issues |
| `results/latest.*` | Current output (json/csv/md) |

## GitHub Actions

- **Weekly run**: Monday 8 AM UTC via `main.yml`
- **Issue-triggered**: `add-repo-from-issue.yml` adds repos from issue URLs

## Environment

- `GITHUB_TOKEN` - Required for higher rate limits (5000 vs 60 req/hr)
- See `.env.example` for template
