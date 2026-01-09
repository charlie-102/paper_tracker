# Changelog

## [Unreleased]

### Added

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
