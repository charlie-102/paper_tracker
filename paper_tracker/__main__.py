"""CLI entry point for Paper Tracker."""

import argparse
import sys
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

    args = parser.parse_args()

    # Initialize tracker
    config_path = args.config
    if config_path is None:
        # Default to config.yaml in package directory
        default_config = Path(__file__).parent / "config.yaml"
        if default_config.exists():
            config_path = str(default_config)

    tracker = PaperTracker(token=args.token, config_path=config_path)

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

    return 0


if __name__ == "__main__":
    sys.exit(main())
