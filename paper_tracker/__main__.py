"""CLI entry point for Paper Tracker."""

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

from .tracker import PaperTracker


def main():
    parser = argparse.ArgumentParser(
        description="Stateful tracker for reproducible low-level vision repos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m paper_tracker                          # Basic search (stateless)
  python -m paper_tracker --history data/history.json  # Stateful search
  python -m paper_tracker -s 50 -y 2024 -d         # Min 50 stars, 2024+, show details
  python -m paper_tracker -o results.json          # Export to JSON
  python -m paper_tracker --csv results.csv        # Export to CSV
  python -m paper_tracker --md results.md          # Export to Markdown

Stateful workflow (for GitHub Actions):
  python -m paper_tracker \\
    --history data/history.json \\
    --md results/latest.md \\
    -o results/latest.json

Environment variables:
  GITHUB_TOKEN         GitHub personal access token (higher rate limits)
  TRACKER_MIN_STARS    Override minimum stars filter
  TRACKER_YEAR         Override year filter
        """
    )

    parser.add_argument(
        "--token", "-t",
        help="GitHub personal access token (or set GITHUB_TOKEN env var)"
    )
    parser.add_argument(
        "--config", "-c",
        help="Path to config.yaml file"
    )
    parser.add_argument(
        "--history",
        help="Path to history.json for stateful tracking (loads and saves state)"
    )
    parser.add_argument(
        "--min-stars", "-s",
        type=int,
        help="Minimum stars filter (default: from config)"
    )
    parser.add_argument(
        "--max-results", "-n",
        type=int,
        help="Max results per query per pass (default: from config)"
    )
    parser.add_argument(
        "--year", "-y",
        help="Filter repos created after this year (default: from config)"
    )
    parser.add_argument(
        "--details", "-d",
        action="store_true",
        help="Show detection details"
    )
    parser.add_argument(
        "--output", "-o",
        help="Export results to JSON file"
    )
    parser.add_argument(
        "--csv",
        help="Export results to CSV file"
    )
    parser.add_argument(
        "--md", "--markdown",
        dest="markdown",
        help="Export results to Markdown file"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress progress output"
    )
    parser.add_argument(
        "--issue-repos",
        help="Path to repos_from_issues.yaml file (repos added via GitHub Issues)"
    )

    # RU Queue arguments
    parser.add_argument(
        "--ru-queue",
        help="Path to ru_queue.yaml file (default: data/ru_queue.yaml)"
    )
    parser.add_argument(
        "--list-ru",
        action="store_true",
        help="List all RU candidates"
    )
    parser.add_argument(
        "--list-ru-pending",
        action="store_true",
        help="List pending RU candidates only"
    )
    parser.add_argument(
        "--add-ru",
        metavar="REPO",
        help="Manually add a repo to RU queue (format: owner/repo)"
    )
    parser.add_argument(
        "--remove-ru",
        metavar="REPO",
        help="Remove a repo from RU queue (format: owner/repo)"
    )
    parser.add_argument(
        "--ru-status",
        nargs=2,
        metavar=("REPO", "STATUS"),
        help="Update RU candidate status (STATUS: pending|processing|completed|skipped)"
    )

    # Archive argument
    parser.add_argument(
        "--archive",
        action="store_true",
        help="Create dated archive copies of output files (e.g., tracker_20260110.json)"
    )

    args = parser.parse_args()

    # Initialize tracker
    config_path = args.config
    if config_path is None:
        # Default to config.yaml in package directory
        default_config = Path(__file__).parent / "config.yaml"
        if default_config.exists():
            config_path = str(default_config)

    # Determine RU queue path
    ru_queue_path = args.ru_queue
    if not ru_queue_path and args.history:
        ru_queue_path = str(Path(args.history).parent / "ru_queue.yaml")

    tracker = PaperTracker(token=args.token, config_path=config_path, ru_queue_path=ru_queue_path)

    # Print header
    if not args.quiet:
        print("Paper Implementation Tracker (Stateful)")
        print(f"Rate limit: {tracker.github.rate_limit.remaining}/{tracker.github.rate_limit.limit}")
        print()

    # Load history if specified
    if args.history:
        tracker.load_history(args.history)
        if not args.quiet:
            print()

    # Handle RU queue commands (these exit early without running search)
    if args.list_ru or args.list_ru_pending:
        status_filter = "pending" if args.list_ru_pending else None
        tracker.print_ru_queue(status_filter)
        return 0

    if args.add_ru:
        if not args.history:
            print("Error: --add-ru requires --history to be set")
            return 1
        tracker.add_to_ru_queue(args.add_ru)
        tracker.ru_queue.save()
        return 0

    if args.remove_ru:
        if not args.history:
            print("Error: --remove-ru requires --history to be set")
            return 1
        tracker.remove_from_ru_queue(args.remove_ru)
        tracker.ru_queue.save()
        return 0

    if args.ru_status:
        repo, status = args.ru_status
        if status not in ("pending", "processing", "completed", "skipped"):
            print(f"Error: Invalid status '{status}'. Use: pending|processing|completed|skipped")
            return 1
        tracker.ru_queue.update_status(repo, status)
        tracker.ru_queue.save()
        print(f"Updated {repo} status to {status}")
        return 0

    # Process repos added via GitHub Issues
    # Look for issue repos file in the same directory as history, or use explicit path
    issue_repos_path = args.issue_repos
    if not issue_repos_path and args.history:
        default_issue_repos = Path(args.history).parent / "repos_from_issues.yaml"
        if default_issue_repos.exists():
            issue_repos_path = str(default_issue_repos)

    if issue_repos_path:
        tracker.process_issue_repos(issue_repos_path)
        if not args.quiet:
            print()

    # Run search
    tracker.search(
        min_stars=args.min_stars,
        max_results=args.max_results,
        year_filter=args.year,
    )

    # Save history if specified
    if args.history:
        tracker.save_history(args.history)

    # Print results
    if not args.quiet:
        tracker.print_results(show_details=args.details)

    # Export
    if args.output:
        tracker.export_json(args.output)
    if args.csv:
        tracker.export_csv(args.csv)
    if args.markdown:
        tracker.export_markdown(args.markdown)

    # Create dated archive copies if requested
    if args.archive:
        date_suffix = datetime.now().strftime("%Y%m%d")
        archived_files = []

        for output_path in [args.output, args.csv, args.markdown]:
            if output_path:
                src = Path(output_path)
                if src.exists():
                    archive_name = f"tracker_{date_suffix}{src.suffix}"
                    archive_path = src.parent / archive_name
                    shutil.copy2(src, archive_path)
                    archived_files.append(str(archive_path))

        if archived_files and not args.quiet:
            print(f"\nArchived to: {', '.join(archived_files)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
