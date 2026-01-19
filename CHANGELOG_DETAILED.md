# Detailed Changelog

> **Complete History** - Full development history with session IDs, commit hashes, and implementation details. For a quick summary, see [CHANGELOG.md](CHANGELOG.md).

Complete development history of the Paper Implementation Tracker.

---

## 2026-01-15

### Hugging Face Trending Papers Analysis [#0646]

Analyzed HuggingFace trending papers to identify current ML research trends and their relevance to the paper tracker project.

### Discussed
- Analyzed HuggingFace trending papers #trending (2026-01-15) [#0646]
  - Top 10 papers with domains, model sizes, and key innovations
  - Domain distribution: LLM Agents (40%), Efficiency (30%), Multimodal (20%), Document/OCR (10%)
  - Notable papers: MiroThinker (72B agent, 81.9% GAIA), SmolDocling (256M compact VLM), vLLM (67.6k stars)
  - Key insight: Current trends lean toward LLM infrastructure/agents rather than low-level vision tasks
  - Full analysis saved to: `/Users/long/.claude/plans/sunny-launching-lamport.md`

---

### Documentation Cleanup and Organization [#7612]

Cleaned up folder organization, updated outdated documentation, and added CLAUDE.md for project knowledge.

### Added
- `CLAUDE.md` with concise project knowledge #docs #cleanup (2026-01-15) [#7612]
  - Architecture overview, quick commands, data flow, key patterns
  - Files: `CLAUDE.md`
- `.env.example` template file #docs #cleanup (2026-01-15) [#7612]
  - Was referenced in DEVELOPMENT.md but missing
  - Files: `.env.example`

### Changed
- Updated `docs/DEVELOPMENT.md` project structure section #docs #cleanup (2026-01-15) [#7612]
  - Added 8+ missing files/folders: web_ui.py, github_search.py, awesome_*.py, parsers/, etc.
  - Files: `docs/DEVELOPMENT.md`
- Added purpose headers to changelog files #docs #cleanup (2026-01-15) [#7612]
  - Cross-references between CHANGELOG.md and CHANGELOG_DETAILED.md
  - Files: `CHANGELOG.md`, `CHANGELOG_DETAILED.md`
- Updated `.gitignore` to track `.env.example` #docs #cleanup (2026-01-15) [#7612]
  - Was incorrectly excluded on line 44
  - Files: `.gitignore`

### Learned
- **Pattern**: Keep both concise and detailed changelogs with cross-references - helps different audiences (quick scan vs deep dive) #docs (2026-01-15) [#7612]
- **Context**: `.env.example` should be tracked in git (not excluded) - template files are meant to be shared #docs (2026-01-15) [#7612]

---

## 2026-01-14

### Add Awesome List Integration for Curated Paper Discovery [#ebee]

Integrated curated "awesome" GitHub lists as a searchable data source to improve discovery of relevant papers/repos beyond GitHub search.

**New Files:**
- `paper_tracker/awesome_parser.py` - Parses markdown tables from awesome list READMEs
  - Extracts: title, model name, conference, year, arXiv ID, GitHub URL
  - Handles flexible table formats with Title/Model/Published/Code columns
  - Conference detection for 18+ venues (CVPR, ECCV, NeurIPS, etc.)

- `paper_tracker/awesome_manager.py` - Manages syncing, caching, and searching curated lists
  - `sync_list()` / `sync_all()` - Fetch and parse awesome lists from GitHub
  - `search()` - Query cached entries by keyword, conference, year
  - `to_search_results()` - Convert to format compatible with existing UI
  - Cache stored in `data/awesome_cache.json`

**Modified Files:**
- `paper_tracker/models.py` - Added `AwesomeEntry` dataclass:
  - Core: `id`, `source_list`, `title`, `model_name`
  - Publication: `conference`, `year`, `arxiv_id`, `paper_url`
  - Code: `github_url`, `github_full_name`, `has_repo`
  - Methods: `to_dict()`, `from_dict()`, `to_repo_format()`

- `paper_tracker/config.yaml` - Added `awesome_lists` configuration:
  ```yaml
  awesome_lists:
    - repo: "ChaofWang/Awesome-Super-Resolution"
      name: "Super Resolution"
      enabled: true
    - repo: "subeeshvasu/Awesome-Deblurring"
    - repo: "hongwang01/Video-and-Single-Image-Deraining"
  ```

- `paper_tracker/web_ui.py` - Added curated search UI:
  - Search source radio: "GitHub", "Curated Lists", "Both"
  - Curated source checkboxes for filtering
  - New "Curated Lists" tab for sync and stats
  - `do_curated_search()`, `do_combined_search()` functions
  - `sync_awesome_lists()`, `get_awesome_stats()` for management

- `paper_tracker/__main__.py` - Added CLI flags:
  - `--sync-awesome` - Sync all configured awesome lists
  - `--awesome-stats` - Show statistics for cached entries

**Usage:**
```bash
# Sync awesome lists
python -m paper_tracker --sync-awesome

# View stats
python -m paper_tracker --awesome-stats

# Web UI: Select "Curated Lists" or "Both" in Search tab
```

**Architecture:**
```
Config (awesome_lists) → AwesomeListManager → GitHubClient (fetch README)
                                           → AwesomeListParser (parse tables)
                                           → Cache (JSON) → Search/UI
```

---

### Fix Search Pagination Bug [#b085]

Fixed pagination failing when navigating to page 2+ with multiple keywords.

**Root Cause:**
When searching with multiple keywords (e.g., "super resolution; image restoration"), each keyword was queried with the same page number. If keyword A had 100 results but keyword B had only 20, page 2 would return empty results for keyword B, causing the combined results to be empty.

**Solution:**
Changed from API-based pagination to local pagination:
1. Fetch all results for all keywords in a single search call
2. Combine, deduplicate, and sort by stars (descending)
3. Store full results in Gradio state
4. Paginate locally from stored results

**Modified Files:**
- `paper_tracker/github_search.py`:
  - `search_fast()` now fetches up to 100 results per keyword, combines and sorts them
  - Removed `page` and `per_page` parameters (UI handles pagination)
  - Returns sorted list instead of (results, count) tuple

- `paper_tracker/web_ui.py`:
  - Added `search_results = gr.State([])` to store full results
  - `do_search()` now returns all results + first page slice
  - `do_search_page()` now slices from stored results (no API call)
  - Updated button handlers to pass/receive results state

---

### Search Optimization & Pagination [#04a2]

Major performance improvements to the search functionality.

**Modified Files:**
- `paper_tracker/github_client.py`:
  - Added `page` parameter for pagination support
  - Returns `(items, total_count)` tuple
  - Added `verify_token()` for GitHub token verification
  - Added `IncompleteRead` error handling for large READMEs
  - Removed `created_after` filter (was too restrictive)

- `paper_tracker/github_search.py`:
  - Added `build_search_query()` - combines keywords + conference + year
  - Added `search_fast()` - instant search without README fetching
  - Added `detect_weights_for_repo()` - on-demand weight detection
  - Changed sort order from stars to relevance

- `paper_tracker/web_ui.py`:
  - Added pagination with Prev/Next buttons (30 per page)
  - Added `current_page` and `total_count` state
  - Added GitHub Settings accordion with token verification
  - Added Select All / Clear buttons for conference filter
  - Changed keyword separator from comma to semicolon
  - Extended year dropdown to 2020-2026
  - Moved weight detection to save phase with progress display

**Performance:**
- Search: ~45+ seconds → <5 seconds (no README fetching)
- Weight detection now runs during save, with progress feedback

**Search Query:**
- Before: `"exact phrase" in:name,description,readme stars:>=20 created:>=2024`
- After: `all words in:name,description,readme stars:>=20` (matches all words, any order)

---

## 2026-01-13

### Model Shop: Search/Shop Tab Separation [#0b00]

Major refactor of the Model Shop web UI to separate GitHub search from model shopping.

**New Files:**
- `paper_tracker/github_search.py` - Stateless GitHub search module with:
  - `GitHubSearcher` class for web UI searches
  - `SEARCH_TEMPLATES` - Quick preset search configurations
  - `save_search_results()` / `load_search_results()` - JSON I/O

**Modified Files:**
- `paper_tracker/web_ui.py` - Complete rewrite with two-tab layout:
  - **Search Tab**: GitHub search with templates, filters, preview table
  - **Shop Tab**: Browse saved repos, filter, cart functionality
- `paper_tracker/ru_sync.py` - Added:
  - `fetch_repo_metadata()` - Fetch stars/description from GitHub API
  - `load_search_results_for_shop()` - Load repos for Shop tab
  - `SEARCH_RESULTS_FILE` - Path constant for search results

**New Data File:**
- `data/search_results.json` - Stores search results for Shop tab

**Features:**
- **Quick Templates**: One-click presets (CVPR'24 Vision, Medical Imaging, etc.)
- **Preview Workflow**: Search results shown before saving, can adjust and re-search
- **Conference Filtering**: Multi-select checkboxes for CVPR, ECCV, NeurIPS, etc.
- **Year Filtering**: Filter by conference year (2024, 2025, 2026)
- **Save Options**: "Save All to DB" or "Save Selected to DB"
- **Enhanced Manual URL**: Now fetches GitHub metadata (stars, description)

**Architecture:**
```
Search Tab:
  Template → Keywords/Conferences/Year → Search → Preview → Save to DB

Shop Tab:
  Refresh (load from JSON) → Filter → Add to Cart → Export Links
```

---

### Model Shop Web UI for Paper-to-RU Workflow [#9ea0]

Added a Gradio-based web interface ("Model Shop") for browsing and managing ML paper repositories with pretrained weights.

**New Files:**
- `paper_tracker/web_ui.py` - Main Gradio web interface
- `paper_tracker/ru_sync.py` - RU unit synchronization module
- `run_web_ui.sh` - Launcher script with hot reload support
- `data/ru_candidates.json` - Cart export storage

**Features:**
- Single-page design with statistics dashboard
- Filterable table of tracked repositories
- Multi-select for adding repos to cart
- Cart system for collecting and exporting GitHub URLs
- Manual URL addition (add to cart or database)
- Sync with existing RU units to exclude already-converted repos
- Modern CSS styling with responsive layout
- Hot reload support for development (`./run_web_ui.sh --reload`)

**Commits:**
- `67ad0fc` - Add Model Shop web UI for paper-to-RU workflow
- `be4dec3` - Update changelog for Model Shop web UI session

---

### Housekeeping

**Commits:**
- `75a2a37` - Remove .claude from tracking and add to .gitignore
- `a749dbc` - Minor updates

---

## 2026-01-12

### Automated Tracker Update

Scheduled GitHub Actions run to update tracker state and cleanup old results.

**Commits:**
- `6faa706` - Update tracker state 2026-01-12 [skip ci]
- `8d9cd2f` - Cleanup old tracker results [skip ci]

---

## 2026-01-10

### Issue-Based Repository Registration Fix

Fixed YAML syntax issues in the GitHub Actions workflow for adding repositories via issues.

**Changes:**
- Converted multiline `gh issue comment` commands to single-line format
- Used `$'...'` quoting with `\n` for newlines
- Fixed YAML indentation rule violations

**Commits:**
- `6bf4ec6` - Fix YAML syntax error in add-repo-from-issue workflow
- `5ed6225` - Fix issue triggering
- `7250ade` - Add repository from issue #1 [skip ci]

### Results Expansion

- `86e21cd` - Expand results
- `81a8e32` - Reformat test.md

### Automated Updates

- `05e9e2c` - Update tracker state 2026-01-10 [skip ci]
- `72d00d5` - Update tracker state 2026-01-10 [skip ci]
- `793aa99` - Cleanup old tracker results [skip ci]
- `7ee3126` - Cleanup old tracker results [skip ci]

---

## 2026-01-09

### Feature: Register Repositories via GitHub Issues

Users can now add repositories to the tracking list by opening a GitHub Issue with a repository URL.

**New Files:**
- `.github/workflows/add-repo-from-issue.yml` - Issue-triggered workflow
- `data/repos_from_issues.yaml` - Intermediate queue for issue-submitted repos

**Modified Files:**
- `paper_tracker/tracker.py` - Added issue repo processing methods:
  - `load_issue_repos()` - Loads URLs from YAML file
  - `process_issue_repos()` - Processes queued repos
  - `_process_issue_repo()` - Single repo processing (skips relevance filter)
  - `_clear_issue_repos()` - Clears queue after processing
- `paper_tracker/__main__.py` - Added `--issue-repos` argument

**Workflow:**
1. User opens GitHub Issue with repo URL (e.g., `https://github.com/owner/repo`)
2. Workflow validates URL and adds to `data/repos_from_issues.yaml`
3. Issue closed with confirmation comment
4. Next scheduled run processes queued repos through detection pipeline
5. Queue file cleared after processing

**Commits:**
- `bbc1af1` - Add feature: register repositories via GitHub Issues

---

### Expanded Conference and Journal Detection

Added 18 new conference and journal detection patterns.

**New Patterns:**
| Category | Added |
|----------|-------|
| **Medical** | MICCAI, ISBI, MIDL |
| **Journals** | TPAMI, IJCV, TIP, TCSVT, TOG, TMM, TNNLS, PR, JMLR |
| **Conferences** | BMVC, ACCV, ICIP, ICPR, IJCAI, 3DV |

**Modified Files:**
- `paper_tracker/detectors.py` - Added new regex patterns

**Commits:**
- `7c0d8b7` - Add more conferences and journals to detection patterns

---

### Documentation Refactor

Split documentation into user-focused and developer-focused views.

**Changes:**
- `README.md` - Now focused on researchers/users:
  - Prominent links to latest results
  - Clear schedule information
  - Brief explanation of what's tracked
- `docs/DEVELOPMENT.md` - All technical documentation:
  - Quick start and CLI options
  - Python API and configuration
  - Project structure and GitHub Actions setup

**Commits:**
- `73f3438` - Refactor docs: separate User and Developer views

---

### Robust Workflow Push Strategy

Fixed workflow push conflicts in GitHub Actions.

**Changes:**
- Fetch and reset to `origin/main` before committing
- Retry push up to 3 times on conflict
- Handles concurrent workflow runs gracefully

**Modified Files:**
- `.github/workflows/main.yml` - Added retry loop and fetch-reset strategy

**Commits:**
- `31cfde0` - Robust push with retry loop and fetch-reset strategy
- `fa89c1c` - Fix workflow push conflicts by adding git pull --rebase

---

### Initial Release

Project initialization with core tracking functionality.

**Core Features:**
- GitHub API client with rate limiting
- Two-pass search strategy (sort by stars + sort by updated)
- Delta check logic for efficient updates
- Weight detection (HuggingFace, Google Drive, GitHub Releases, etc.)
- Conference detection (CVPR, ECCV, ICCV, NeurIPS, ICML, etc.)
- "Coming Soon" detection for promised weights
- Fresh release detection (weights released in last 7 days)
- Stateful tracking with history.json
- Multiple export formats (JSON, CSV, Markdown)

**CLI Options:**
- `--history` - Stateful tracking
- `--token` - GitHub authentication
- `--config` - Custom configuration
- `--min-stars` - Stars filter
- `--year` - Year filter
- `--archive` - Dated archive copies
- Multiple output format flags

**RU Queue System:**
- Auto-queue repos with `HAS_WEIGHTS` + arXiv ID
- Manual queue management via CLI
- Status tracking (pending/processing/completed/skipped)

**Project Structure:**
```
paper_tracker/
├── paper_tracker/           # Python package
│   ├── __main__.py          # CLI entry point
│   ├── tracker.py           # Main stateful tracker
│   ├── detectors.py         # Detection logic
│   ├── github_client.py     # GitHub API client
│   ├── models.py            # Data models
│   └── config.yaml          # Configuration
├── .github/workflows/       # GitHub Actions
├── data/                    # Persistent state
├── results/                 # Output files
└── tests/                   # Test suite
```

**GitHub Actions Workflow:**
- Weekly scheduled runs (Monday 8:00 AM UTC)
- Manual trigger support
- Auto-commit results with `[skip ci]`

**Commits:**
- `328be4b` - Set up action
- `b49202b` - Init
- `588cf5b` - Initial commit

---

## Unreleased Features

Features documented in CHANGELOG.md but not yet tagged:

### RU (Reproducible Unit) Queue System
- Auto-queues repos with `HAS_WEIGHTS` status + arXiv ID
- Manual queue management via CLI
- Queue stored in `data/ru_queue.yaml`
- CLI arguments: `--ru-queue`, `--list-ru`, `--list-ru-pending`, `--add-ru`, `--remove-ru`, `--ru-status`

### Automatic Dated Archive Creation
- `--archive` flag creates dated copies of output files
- Format: `results/tracker_YYYYMMDD.json`, `results/tracker_YYYYMMDD.md`

### Expanded Search Coverage
- 24 new search queries (8 → 32 total)
- Categories: low-level vision, video processing, medical imaging, conference-based
- ~40 new relevance keywords

### Conference Re-detection Fix
- Repos with `HAS_WEIGHTS` status now re-run conference detection
- Allows new conference patterns to apply to existing repos
