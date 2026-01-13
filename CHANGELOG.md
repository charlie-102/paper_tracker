# Changelog

## 2026-01-13

### Session: Model Shop Web UI for Paper-to-RU Workflow [#9ea0]

- **Added**: Gradio web interface ("Model Shop") for browsing and selecting ML paper repos #webui
  - Files: `paper_tracker/web_ui.py`, `paper_tracker/ru_sync.py`, `run_web_ui.sh`
- **Added**: RU unit synchronization to exclude already-converted repos from candidates #webui
  - Files: `paper_tracker/ru_sync.py`
- **Added**: Cart system for collecting repos and exporting GitHub URLs #webui
  - Files: `data/ru_candidates.json`
- **Added**: Manual URL addition (add to cart or add to database) #webui
- **Added**: Hot reload support for development (`./run_web_ui.sh --reload`) #webui
- **Changed**: Modern single-page UI design with stats, filters, and styled components #webui

---

## [Unreleased]

### Added

#### RU (Reproducible Unit) Queue System

New system to track repositories as candidates for Reproducible Unit generation.

**Features:**
- Auto-queues repos with `HAS_WEIGHTS` status + arXiv ID when loading history or during search
- Manual queue management via CLI
- Queue stored in `data/ru_queue.yaml`

**New CLI Arguments:**
- `--ru-queue PATH` - Custom queue file path
- `--list-ru` - List all RU candidates
- `--list-ru-pending` - List pending candidates only
- `--add-ru REPO` - Manually add repo (format: owner/repo)
- `--remove-ru REPO` - Remove from queue
- `--ru-status REPO STATUS` - Update status (pending|processing|completed|skipped)

**Files Modified:**
- `paper_tracker/tracker.py` - Added `RUCandidate`, `RUQueueManager` classes
- `paper_tracker/models.py` - Added `ru_candidate` field to `RepoInfo`
- `paper_tracker/__main__.py` - Added RU CLI arguments

#### Automatic Dated Archive Creation

New `--archive` flag creates dated copies of output files.

```bash
python -m paper_tracker --history data/history.json \
  --md results/latest.md \
  -o results/latest.json \
  --archive
# Creates: results/tracker_20260110.json, results/tracker_20260110.md
```

#### Expanded Search Coverage

Added 24 new search queries covering:
- **Low-level vision:** deraining, dehazing, low-light enhancement, shadow removal, HDR, desnowing, JPEG artifacts, demosaicing, face restoration
- **Video processing:** video denoising, restoration, deblurring, frame interpolation, enhancement
- **Medical imaging:** CT denoising, MRI reconstruction, medical image enhancement
- **Conference-based:** CVPR/ECCV/NeurIPS/MICCAI pretrained queries

Added ~40 new relevance keywords for better filtering.

**Files Modified:**
- `paper_tracker/config.yaml` - Expanded queries (8 → 32) and keywords

### Fixed

#### Conference Re-detection for Stable Repos

Previously, repos with `HAS_WEIGHTS` status (Case A) skipped all detection including conference detection. Now conference detection always runs, allowing new conference patterns to apply to existing repos.

**Files Modified:**
- `paper_tracker/tracker.py` - Modified `_process_repo_with_delta()` Case A

---

#### New Feature: Add Repositories via GitHub Issues

Users can now add repositories to the tracking list by opening a GitHub Issue with a repository URL.

**Files Created:**

1. **`.github/workflows/add-repo-from-issue.yml`** - New GitHub Actions workflow that:
   - Triggers when a GitHub Issue is opened
   - Parses the GitHub repository URL from the issue body
   - Validates the URL exists on GitHub
   - Checks for duplicates (in `history.json` or already queued)
   - Adds valid repos to `data/repos_from_issues.yaml`
   - Posts a confirmation comment and closes the issue on success
   - Posts an error comment (without closing) if no valid URL found

2. **`data/repos_from_issues.yaml`** - Intermediate data file to store repos queued from issues

**Files Modified:**

1. **`paper_tracker/tracker.py`** - Added methods:
   - `load_issue_repos()` - Loads URLs from the YAML file
   - `process_issue_repos()` - Processes queued repos through the detection pipeline
   - `_process_issue_repo()` - Processes a single repo (skips relevance filter)
   - `_clear_issue_repos()` - Clears the YAML file after processing

2. **`paper_tracker/__main__.py`** - Added:
   - `--issue-repos` argument (optional)
   - Auto-detection of `repos_from_issues.yaml` in same directory as history file
   - Processing of issue repos before the normal search

**How It Works:**

1. User opens a GitHub Issue with a repo URL (e.g., `https://github.com/owner/repo`)
2. The issue workflow validates and adds it to `data/repos_from_issues.yaml`
3. Issue is closed with a confirmation comment
4. During the next scheduled update:
   - The tracker automatically finds `data/repos_from_issues.yaml`
   - Processes each queued repo through the same detection pipeline
   - Repos appear in `results/latest.md` just like any other tracked repo
   - The queue file is cleared

**What Was NOT Changed:**

- The main scheduled workflow (`main.yml`) - unchanged
- Pretrained weight detection logic - unchanged
- `results/latest.md` generation - unchanged
- All existing functionality - unchanged
