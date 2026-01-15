"""
Paper-to-RU Model Shop - Two-tab UI for searching and shopping ML paper repos.

Tab 1: Search - Find repos on GitHub with preview and save
Tab 2: Shop - Browse saved repos, filter, and add to cart

Usage:
    python -m paper_tracker.web_ui
    ./run_web_ui.sh --reload  # Hot reload mode
"""

import gradio as gr
import pandas as pd
from datetime import datetime

try:
    from .github_search import (
        GitHubSearcher,
        SEARCH_TEMPLATES,
        save_search_results,
        load_search_results,
    )
    from .ru_sync import (
        get_existing_ru_units,
        sync_candidates,
        load_candidate_status,
        save_candidate_status,
        export_cart_links,
        add_manual_repo,
        load_search_results_for_shop,
        is_in_ru,
        RU_UNITS_PATH,
    )
    from .awesome_manager import AwesomeListManager, get_awesome_manager
except ImportError:
    from github_search import (
        GitHubSearcher,
        SEARCH_TEMPLATES,
        save_search_results,
        load_search_results,
    )
    from ru_sync import (
        get_existing_ru_units,
        sync_candidates,
        load_candidate_status,
        save_candidate_status,
        export_cart_links,
        add_manual_repo,
        load_search_results_for_shop,
        is_in_ru,
        RU_UNITS_PATH,
    )
    from awesome_manager import AwesomeListManager, get_awesome_manager


# Custom CSS for beautiful UI
CUSTOM_CSS = """
/* Modern color scheme */
:root {
    --primary: #6366f1;
    --primary-hover: #4f46e5;
    --success: #10b981;
    --danger: #ef4444;
    --warning: #f59e0b;
    --gray-50: #f9fafb;
    --gray-100: #f3f4f6;
    --gray-200: #e5e7eb;
    --gray-600: #4b5563;
    --gray-900: #111827;
}

/* Container */
.gradio-container {
    max-width: 1400px !important;
    margin: 0 auto !important;
}

/* Header styling */
.header-title {
    background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-size: 2.5rem !important;
    font-weight: 800 !important;
    margin-bottom: 0 !important;
}

/* Template buttons */
.template-btn {
    font-size: 0.85rem !important;
    padding: 8px 12px !important;
}

/* Filter section */
.filter-section {
    background: var(--gray-50);
    border-radius: 16px;
    padding: 20px;
    margin: 16px 0;
}

/* Table styling */
.dataframe {
    border-radius: 12px !important;
    overflow: hidden !important;
}

/* Preview warning */
.preview-warning {
    background: #fef3c7;
    border-left: 4px solid #f59e0b;
    padding: 12px 16px;
    border-radius: 0 8px 8px 0;
    margin: 16px 0;
}

/* Cart section */
.cart-section {
    background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
    border-radius: 16px;
    padding: 20px;
    margin-top: 24px;
}

/* Buttons */
.primary-btn {
    background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%) !important;
    border: none !important;
    color: white !important;
    font-weight: 600 !important;
    padding: 12px 24px !important;
    border-radius: 10px !important;
    transition: transform 0.2s, box-shadow 0.2s !important;
}

.primary-btn:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 4px 12px rgba(99, 102, 241, 0.4) !important;
}

/* Links output */
.links-box textarea {
    font-family: 'SF Mono', 'Fira Code', monospace !important;
    font-size: 0.9rem !important;
    background: var(--gray-900) !important;
    color: #10b981 !important;
    border-radius: 12px !important;
    padding: 16px !important;
}

/* Tab styling */
.tabs {
    margin-top: 20px;
}
"""

# Conference options for checkboxes
CONFERENCE_OPTIONS = [
    "CVPR", "ECCV", "ICCV", "NeurIPS", "ICML", "ICLR",
    "AAAI", "MICCAI", "SIGGRAPH", "WACV", "BMVC", "TPAMI"
]


# =============================================================================
# SEARCH TAB FUNCTIONS
# =============================================================================

def check_github_token():
    """Check GitHub token status and return formatted status."""
    from .github_client import GitHubClient
    import os

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return "**Token Status:** Not configured. Set `GITHUB_TOKEN` env var for higher rate limits."

    try:
        client = GitHubClient(token)
        info = client.verify_token()

        if info["authenticated"]:
            return f"**Token Status:** ✓ Authenticated | Limit: {info['limit']}/hr | Remaining: {info['remaining']}"
        else:
            return f"**Token Status:** ⚠ Unauthenticated (invalid token?) | Limit: {info['limit']}/hr"
    except Exception as e:
        return f"**Token Status:** ✗ Error checking token: {str(e)}"


def apply_template(template_name: str):
    """Apply a search template to populate fields."""
    if template_name not in SEARCH_TEMPLATES:
        return gr.update(), gr.update(), gr.update()

    template = SEARCH_TEMPLATES[template_name]
    return (
        template.get("keywords", ""),
        template.get("conferences", []),
        template.get("year", "2024"),
    )


def _make_progress_bar(value: int, max_val: int = 100) -> str:
    """Generate HTML progress bar."""
    pct = int((value / max_val) * 100) if max_val > 0 else 0
    return f'<progress value="{pct}" max="100" style="width:100%; height:20px;"></progress>'


RESULTS_PER_PAGE = 30


def do_search(keywords_str: str, conferences: list, year: str, min_stars: int):
    """Fast GitHub search - fetches all results, returns first page."""
    if not keywords_str.strip():
        return pd.DataFrame(), "Enter keywords to search", "", 1, 0, []

    # Split by semicolon (allows commas in search terms)
    keywords = [k.strip() for k in keywords_str.split(";") if k.strip()]

    try:
        searcher = GitHubSearcher()

        # Fetch all results (search_fast now returns all results sorted by stars)
        all_results = searcher.search_fast(
            keywords=keywords,
            conferences=conferences or [],
            year=year if year != "Any" else None,
            min_stars=min_stars,
        )

        if not all_results:
            return pd.DataFrame(), "No repos found matching criteria", "", 1, 0, []

        total_count = len(all_results)
        total_pages = (total_count + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE

        # Get first page slice
        page_results = all_results[:RESULTS_PER_PAGE]

        # Build dataframe for first page
        rows = []
        for repo in page_results:
            rows.append({
                "Select": False,
                "Repository": f"[{repo['name']}]({repo['url']})",
                "Stars": repo.get("stars", 0),
                "Description": (repo.get("description") or "-")[:100],
                "full_name": repo["full_name"],
            })

        df = pd.DataFrame(rows)
        status = f"Page 1/{total_pages} ({total_count} total results)"
        return df, status, "", 1, total_count, all_results

    except Exception as e:
        return pd.DataFrame(), f"Search error: {str(e)}", "", 1, 0, []


def do_search_page(all_results: list, current_page: int, total_count: int, direction: str):
    """Navigate to next/previous page using stored results."""
    if not all_results:
        return pd.DataFrame(), "No results. Run a search first.", "", 1, 0, []

    total_pages = (total_count + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE

    if direction == "next":
        new_page = min(current_page + 1, total_pages)
    elif direction == "prev":
        new_page = max(1, current_page - 1)
    else:
        new_page = current_page

    # Calculate slice for the requested page
    start_idx = (new_page - 1) * RESULTS_PER_PAGE
    end_idx = start_idx + RESULTS_PER_PAGE
    page_results = all_results[start_idx:end_idx]

    if not page_results:
        return pd.DataFrame(), f"No more results (page {new_page})", "", new_page, total_count, all_results

    # Build dataframe for this page
    rows = []
    for repo in page_results:
        rows.append({
            "Select": False,
            "Repository": f"[{repo['name']}]({repo['url']})",
            "Stars": repo.get("stars", 0),
            "Description": (repo.get("description") or "-")[:100],
            "full_name": repo["full_name"],
        })

    df = pd.DataFrame(rows)
    status = f"Page {new_page}/{total_pages} ({total_count} total results)"
    return df, status, "", new_page, total_count, all_results


def do_curated_search(query: str, sources: list, conference: str, year: str, has_code_only: bool):
    """Search in curated awesome lists."""
    try:
        manager = get_awesome_manager()

        # Convert sources to full repo names if needed
        source_repos = None
        if sources:
            configured = manager.get_configured_sources()
            source_repos = [s["repo"] for s in configured if s["name"] in sources]

        results = manager.search(
            query=query,
            sources=source_repos,
            conference=conference if conference and conference != "All" else None,
            year=year if year and year != "Any" else None,
            has_code_only=has_code_only,
        )

        if not results:
            return pd.DataFrame(), "No entries found in curated lists", "", 1, 0, []

        # Convert to search results format
        all_results = manager.to_search_results(results, include_no_code=not has_code_only)
        total_count = len(all_results)
        total_pages = (total_count + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE

        # Get first page
        page_results = all_results[:RESULTS_PER_PAGE]

        rows = []
        for repo in page_results:
            url = repo.get("url", "")
            name = repo.get("name", "Unknown")
            repo_link = f"[{name}]({url})" if url else name
            rows.append({
                "Select": False,
                "Repository": repo_link,
                "Stars": repo.get("stars", 0),
                "Description": (repo.get("description") or "-")[:100],
                "full_name": repo.get("full_name", ""),
            })

        df = pd.DataFrame(rows)
        status = f"Page 1/{total_pages} ({total_count} curated entries)"
        return df, status, "", 1, total_count, all_results

    except Exception as e:
        return pd.DataFrame(), f"Search error: {str(e)}", "", 1, 0, []


def do_combined_search(
    keywords_str: str,
    conferences: list,
    year: str,
    min_stars: int,
    curated_sources: list,
    has_code_only: bool
):
    """Search both GitHub and curated lists, merge results."""
    github_results = []
    curated_results = []

    # Search GitHub
    if keywords_str.strip():
        keywords = [k.strip() for k in keywords_str.split(";") if k.strip()]
        try:
            searcher = GitHubSearcher()
            github_results = searcher.search_fast(
                keywords=keywords,
                conferences=conferences or [],
                year=year if year != "Any" else None,
                min_stars=min_stars,
            )
        except Exception as e:
            print(f"GitHub search error: {e}")

    # Search curated lists
    try:
        manager = get_awesome_manager()
        source_repos = None
        if curated_sources:
            configured = manager.get_configured_sources()
            source_repos = [s["repo"] for s in configured if s["name"] in curated_sources]

        entries = manager.search(
            query=keywords_str,
            sources=source_repos,
            conference=conferences[0] if conferences else None,
            year=year if year != "Any" else None,
            has_code_only=has_code_only,
        )
        curated_results = manager.to_search_results(entries, include_no_code=not has_code_only)
    except Exception as e:
        print(f"Curated search error: {e}")

    # Merge results (dedupe by full_name, prefer GitHub data for star counts)
    merged = {}
    for repo in github_results:
        full_name = repo["full_name"]
        merged[full_name] = repo
        merged[full_name]["_source"] = "github"

    for repo in curated_results:
        full_name = repo.get("full_name", "")
        if not full_name or full_name.startswith("paper:"):
            # No GitHub repo, add as paper-only
            key = repo.get("_entry_id", repo.get("name", ""))
            if key not in merged:
                merged[key] = repo
                merged[key]["_source"] = "curated"
        elif full_name in merged:
            # Enhance with curated metadata
            merged[full_name]["_source"] = "both"
        else:
            merged[full_name] = repo
            merged[full_name]["_source"] = "curated"

    all_results = list(merged.values())
    # Sort by stars descending
    all_results.sort(key=lambda x: x.get("stars", 0), reverse=True)

    if not all_results:
        return pd.DataFrame(), "No results found", "", 1, 0, []

    total_count = len(all_results)
    total_pages = (total_count + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE
    page_results = all_results[:RESULTS_PER_PAGE]

    rows = []
    for repo in page_results:
        url = repo.get("url", "")
        name = repo.get("name", "Unknown")
        repo_link = f"[{name}]({url})" if url else name
        rows.append({
            "Select": False,
            "Repository": repo_link,
            "Stars": repo.get("stars", 0),
            "Description": (repo.get("description") or "-")[:100],
            "full_name": repo.get("full_name", ""),
        })

    df = pd.DataFrame(rows)
    gh_count = sum(1 for r in all_results if r.get("_source") in ("github", "both"))
    cur_count = sum(1 for r in all_results if r.get("_source") in ("curated", "both"))
    status = f"Page 1/{total_pages} ({total_count} total: {gh_count} GitHub, {cur_count} curated)"
    return df, status, "", 1, total_count, all_results


def sync_awesome_lists():
    """Sync all configured awesome lists."""
    try:
        manager = get_awesome_manager()
        results = manager.sync_all(force=True)

        status_lines = []
        for repo, count in results.items():
            if count >= 0:
                status_lines.append(f"{repo.split('/')[-1]}: {count} entries")
            else:
                status_lines.append(f"{repo.split('/')[-1]}: Error")

        return "\n".join(status_lines) if status_lines else "No lists configured"
    except Exception as e:
        return f"Error syncing: {str(e)}"


def get_awesome_stats():
    """Get statistics about cached awesome list entries."""
    try:
        manager = get_awesome_manager()
        stats = manager.get_stats()
        sources = manager.get_configured_sources()

        rows = []
        for source in sources:
            rows.append({
                "Source": source["name"],
                "Entries": source["entry_count"],
                "With Code": source["entries_with_code"],
                "Last Sync": source["last_synced"][:10] if source["last_synced"] != "Never" else "Never",
            })

        df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["Source", "Entries", "With Code", "Last Sync"])
        total_msg = f"Total: {stats['total_entries']} entries ({stats['entries_with_code']} with code)"
        return df, total_msg
    except Exception as e:
        return pd.DataFrame(), f"Error: {str(e)}"


def get_curated_source_choices():
    """Get list of curated source names for checkbox."""
    try:
        manager = get_awesome_manager()
        sources = manager.get_configured_sources()
        return [s["name"] for s in sources if s["enabled"]]
    except Exception:
        return []


def save_all_to_db(preview_df: pd.DataFrame, keywords_str: str, conferences: list, year: str, min_stars: int):
    """Save all preview results with weight detection."""
    if preview_df is None or len(preview_df) == 0:
        yield "No results to save"
        return

    keywords = [k.strip() for k in keywords_str.split(";") if k.strip()]
    repo_names = preview_df["full_name"].tolist()

    try:
        searcher = GitHubSearcher()
        results = []

        # Detect weights for each repo (this is the slow part)
        for i, full_name in enumerate(repo_names):
            yield f"Checking weights for repo {i+1}/{len(repo_names)}..."

            # Get basic info from preview
            row = preview_df[preview_df["full_name"] == full_name].iloc[0]

            # Detect weights
            weight_info = searcher.detect_weights_for_repo(full_name)

            results.append({
                "full_name": full_name,
                "name": full_name.split("/")[1],
                "url": f"https://github.com/{full_name}",
                "stars": int(row["Stars"]),
                "description": row.get("Description", ""),
                "weight_status": weight_info["weight_status"],
                "weight_details": weight_info["weight_details"],
                "conference": "",  # Not detected in fast search
                "conference_year": "",
            })

        query_info = {
            "keywords": keywords,
            "conferences": conferences,
            "conference_year": year,
            "min_stars": min_stars,
        }

        save_search_results(results, query_info)
        yield f"Saved {len(results)} repos with weight info"

    except Exception as e:
        yield f"Error saving: {str(e)}"


def save_selected_to_db(preview_df: pd.DataFrame, keywords_str: str, conferences: list, year: str, min_stars: int):
    """Save selected repos with weight detection."""
    if preview_df is None or len(preview_df) == 0:
        yield "No results to save"
        return

    selected = preview_df[preview_df["Select"] == True]
    if len(selected) == 0:
        yield "No repos selected"
        return

    keywords = [k.strip() for k in keywords_str.split(";") if k.strip()]
    repo_names = selected["full_name"].tolist()

    try:
        searcher = GitHubSearcher()
        results = []

        # Detect weights for each selected repo
        for i, full_name in enumerate(repo_names):
            yield f"Checking weights for repo {i+1}/{len(repo_names)}..."

            row = selected[selected["full_name"] == full_name].iloc[0]

            # Detect weights
            weight_info = searcher.detect_weights_for_repo(full_name)

            results.append({
                "full_name": full_name,
                "name": full_name.split("/")[1],
                "url": f"https://github.com/{full_name}",
                "stars": int(row["Stars"]),
                "description": row.get("Description", ""),
                "weight_status": weight_info["weight_status"],
                "weight_details": weight_info["weight_details"],
                "conference": "",
                "conference_year": "",
            })

        query_info = {
            "keywords": keywords,
            "conferences": conferences,
            "conference_year": year,
            "min_stars": min_stars,
            "selection": "manual",
        }

        save_search_results(results, query_info)
        yield f"Saved {len(results)} selected repos with weight info"

    except Exception as e:
        yield f"Error saving: {str(e)}"


# =============================================================================
# SHOP TAB FUNCTIONS
# =============================================================================

def get_stats(repos: list, ru_units: dict) -> tuple:
    """Get statistics for display."""
    # Filter out RU units
    candidates = [r for r in repos if not is_in_ru(r.get("name", ""), ru_units)]

    total = len(candidates)
    hf_count = sum(1 for r in candidates if r.get("weight_status") == "HF")
    cloud_count = sum(1 for r in candidates if r.get("weight_status") in ("Cloud", "GDrive", "Baidu"))
    release_count = sum(1 for r in candidates if r.get("weight_status") == "Release")

    return total, hf_count, cloud_count, release_count


def build_shop_dataframe(repos: list, ru_units: dict, cart: set) -> pd.DataFrame:
    """Build DataFrame for shop table (excluding RU units and cart items)."""
    rows = []

    for repo in repos:
        name = repo.get("name", "")
        full_name = repo.get("full_name", "")

        # Skip if in RU or cart
        if is_in_ru(name, ru_units):
            continue
        if full_name in cart:
            continue

        conf = repo.get("conference", "")
        year = repo.get("conference_year", "")
        if conf and year:
            conf_display = f"{conf}'{year[-2:]}" if len(year) >= 2 else conf
        elif conf:
            conf_display = conf
        else:
            conf_display = "-"

        url = repo.get("url", f"https://github.com/{full_name}")
        repo_link = f"[{name}]({url})"

        rows.append({
            "Add": False,
            "Repository": repo_link,
            "Stars": repo.get("stars", 0),
            "Conference": conf_display,
            "Source": repo.get("weight_status", "-") or "-",
            "full_name": full_name,
        })

    df = pd.DataFrame(rows)
    if len(df) > 0:
        df = df.sort_values("Stars", ascending=False).reset_index(drop=True)

    return df


def refresh_shop():
    """Refresh shop data from search_results.json."""
    ru_units = get_existing_ru_units(RU_UNITS_PATH)
    repos = load_search_results_for_shop()
    status_data = load_candidate_status()
    cart = set(status_data.get("cart", []))

    df = build_shop_dataframe(repos, ru_units, cart)
    total, hf_count, cloud_count, release_count = get_stats(repos, ru_units)
    links = export_cart_links(status_data)

    status = f"Loaded {len(repos)} repos ({len(ru_units)} RU units excluded)"

    return (
        df,  # table
        f"**{total}**\nAvailable",  # stat1
        f"**{len(cart)}**\nIn Cart",  # stat2
        f"**{hf_count}**\nHuggingFace",  # stat3
        f"**{cloud_count}**\nCloud",  # stat4
        links,  # cart links
        status,  # status message
        df,  # state
    )


def filter_shop_dataframe(df: pd.DataFrame, search: str, conference: str, source: str, min_stars: int) -> pd.DataFrame:
    """Filter the shop dataframe."""
    if df is None or len(df) == 0:
        return df

    filtered = df.copy()

    if search:
        filtered = filtered[filtered["Repository"].str.lower().str.contains(search.lower(), na=False)]

    if conference and conference != "All":
        filtered = filtered[filtered["Conference"].str.contains(conference, case=False, na=False)]

    if source and source != "All":
        filtered = filtered[filtered["Source"] == source]

    if min_stars > 0:
        filtered = filtered[filtered["Stars"] >= min_stars]

    return filtered


def add_to_cart(df: pd.DataFrame):
    """Add selected repos to cart."""
    if df is None or len(df) == 0:
        status_data = load_candidate_status()
        return "No repos available", df, export_cart_links(status_data), df

    status_data = load_candidate_status()
    cart = set(status_data.get("cart", []))

    selected = df[df["Add"] == True]
    if len(selected) == 0:
        return "Select repos first", df, export_cart_links(status_data), df

    added = 0
    for _, row in selected.iterrows():
        full_name = row["full_name"]
        if full_name not in cart:
            cart.add(full_name)
            added += 1

    status_data["cart"] = list(cart)
    save_candidate_status(status_data)

    # Rebuild table without cart items
    ru_units = get_existing_ru_units(RU_UNITS_PATH)
    repos = load_search_results_for_shop()
    new_df = build_shop_dataframe(repos, ru_units, cart)

    return f"Added {added} repos to cart", new_df, export_cart_links(status_data), new_df


def add_url_to_cart(url: str):
    """Add URL directly to cart with metadata fetch."""
    if not url or not url.strip():
        return "Enter a URL", url, gr.update(), gr.update()

    status_data = load_candidate_status()
    success, msg = add_manual_repo(url.strip(), status_data, fetch_metadata=True)

    if success:
        full_name = url.strip().replace("https://github.com/", "").rstrip("/")
        cart = set(status_data.get("cart", []))
        cart.add(full_name)
        status_data["cart"] = list(cart)
        save_candidate_status(status_data)

        ru_units = get_existing_ru_units(RU_UNITS_PATH)
        repos = load_search_results_for_shop()
        df = build_shop_dataframe(repos, ru_units, cart)

        return msg, "", export_cart_links(status_data), df

    return msg, url, gr.update(), gr.update()


def add_url_to_db(url: str):
    """Add URL to database only (not cart)."""
    if not url or not url.strip():
        return "Enter a URL", url, gr.update()

    # Add to search results file
    try:
        from .ru_sync import fetch_repo_metadata
    except ImportError:
        from ru_sync import fetch_repo_metadata

    metadata = fetch_repo_metadata(url.strip())
    if not metadata:
        return "Could not fetch repo info", url, gr.update()

    # Load and append to search results
    repos, query_info = load_search_results()
    full_name = metadata["full_name"]

    # Check if already exists
    if any(r["full_name"] == full_name for r in repos):
        return f"{metadata['name']} already in database", "", gr.update()

    repos.append(metadata)
    save_search_results(repos, query_info)

    # Refresh shop table
    ru_units = get_existing_ru_units(RU_UNITS_PATH)
    status_data = load_candidate_status()
    cart = set(status_data.get("cart", []))
    df = build_shop_dataframe(repos, ru_units, cart)

    return f"Added {metadata['name']} ({metadata['stars']} stars) to DB", "", df


def clear_cart():
    """Clear cart."""
    status_data = load_candidate_status()
    status_data["cart"] = []
    save_candidate_status(status_data)

    ru_units = get_existing_ru_units(RU_UNITS_PATH)
    repos = load_search_results_for_shop()
    df = build_shop_dataframe(repos, ru_units, set())

    return "Cart cleared", df, "", df


# =============================================================================
# UI CREATION
# =============================================================================

def create_ui():
    """Create the two-tab Model Shop UI."""

    with gr.Blocks(title="Model Shop") as app:

        # Header
        gr.HTML("""
            <div style="text-align: center; padding: 20px 0;">
                <h1 style="font-size: 2.5rem; font-weight: 800;
                    background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
                    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
                    margin-bottom: 8px;">
                    Model Shop
                </h1>
                <p style="color: #6b7280; font-size: 1.1rem;">
                    Search GitHub for ML paper repos, then shop and export
                </p>
            </div>
        """)

        with gr.Tabs() as tabs:

            # =================================================================
            # TAB 1: SEARCH
            # =================================================================
            with gr.TabItem("Search", id="search_tab"):

                # GitHub Settings Accordion
                with gr.Accordion("GitHub Settings", open=False):
                    with gr.Row():
                        token_status = gr.Markdown("**Token Status:** Click 'Check Token' to verify")
                        check_token_btn = gr.Button("Check Token", size="sm", scale=0)
                    gr.Markdown(
                        "*Set `GITHUB_TOKEN` environment variable for higher rate limits (5000/hr vs 60/hr)*"
                    )

                gr.Markdown("### Quick Templates")
                with gr.Row():
                    template_btns = {}
                    for name in SEARCH_TEMPLATES:
                        template_btns[name] = gr.Button(name, size="sm", elem_classes="template-btn")

                gr.Markdown("### Search Source")
                with gr.Row():
                    search_source = gr.Radio(
                        choices=["GitHub", "Curated Lists", "Both"],
                        value="GitHub",
                        label="Search in",
                        scale=2
                    )
                    has_code_only = gr.Checkbox(
                        label="Has Code Only",
                        value=True,
                        scale=1,
                        info="Only show entries with GitHub repos"
                    )

                curated_sources = gr.CheckboxGroup(
                    choices=get_curated_source_choices(),
                    label="Curated Sources (for Curated/Both modes)",
                    value=get_curated_source_choices(),
                    visible=True,
                )

                gr.Markdown("### Search Parameters")

                keywords_input = gr.Textbox(
                    label="Keywords (semicolon-separated)",
                    placeholder="image restoration; super resolution; implicit neural representation",
                    lines=1,
                )

                conferences_input = gr.CheckboxGroup(
                    choices=CONFERENCE_OPTIONS,
                    label="Filter by Conference (empty = all)",
                    value=[],
                )
                with gr.Row():
                    select_all_conf_btn = gr.Button("Select All", size="sm", scale=0)
                    clear_conf_btn = gr.Button("Clear", size="sm", scale=0)

                with gr.Row():
                    year_input = gr.Dropdown(
                        choices=["Any", "2020", "2021", "2022", "2023", "2024", "2025", "2026"],
                        value="2024",
                        label="Conference Year",
                    )
                    stars_input = gr.Slider(
                        minimum=0,
                        maximum=500,
                        value=20,
                        step=10,
                        label="Min Stars",
                    )

                search_btn = gr.Button("Search GitHub", variant="primary")

                # Pagination state
                current_page = gr.State(1)
                total_count = gr.State(0)
                search_results = gr.State([])  # Store all results for local pagination

                # Preview section
                gr.Markdown("### Preview Results")
                search_status = gr.Markdown("*Click Search to find repos*")
                search_progress = gr.HTML("")

                preview_table = gr.Dataframe(
                    headers=["Select", "Repository", "Stars", "Description"],
                    datatype=["bool", "markdown", "number", "str"],
                    interactive=True,
                    wrap=True,
                )

                # Pagination controls
                with gr.Row():
                    prev_btn = gr.Button("← Previous", size="sm", scale=0)
                    next_btn = gr.Button("Next →", size="sm", scale=0)

                gr.HTML("""
                    <div class="preview-warning">
                        Preview only - adjust filters and re-search as needed.
                        Click "Save to DB" when satisfied.
                    </div>
                """)

                with gr.Row():
                    save_all_btn = gr.Button("Save All to DB", variant="primary")
                    save_selected_btn = gr.Button("Save Selected to DB", variant="secondary")

                save_status = gr.Markdown("")

                # GitHub token check handler
                check_token_btn.click(
                    check_github_token,
                    outputs=token_status,
                )

                # Conference filter button handlers
                select_all_conf_btn.click(
                    fn=lambda: CONFERENCE_OPTIONS,
                    outputs=conferences_input,
                )
                clear_conf_btn.click(
                    fn=lambda: [],
                    outputs=conferences_input,
                )

                # Template button handlers
                for name, btn in template_btns.items():
                    btn.click(
                        lambda n=name: apply_template(n),
                        outputs=[keywords_input, conferences_input, year_input],
                    )

                # Search dispatcher based on source selection
                def dispatch_search(source, keywords, conferences, year, min_stars, curated_srcs, code_only):
                    if source == "GitHub":
                        return do_search(keywords, conferences, year, min_stars)
                    elif source == "Curated Lists":
                        return do_curated_search(keywords, curated_srcs, conferences[0] if conferences else None, year, code_only)
                    else:  # Both
                        return do_combined_search(keywords, conferences, year, min_stars, curated_srcs, code_only)

                # Search button handler (starts at page 1)
                search_btn.click(
                    dispatch_search,
                    inputs=[search_source, keywords_input, conferences_input, year_input, stars_input, curated_sources, has_code_only],
                    outputs=[preview_table, search_status, search_progress, current_page, total_count, search_results],
                )

                # Pagination handlers - use stored results for local pagination
                prev_btn.click(
                    lambda results, page, total: do_search_page(results, page, total, "prev"),
                    inputs=[search_results, current_page, total_count],
                    outputs=[preview_table, search_status, search_progress, current_page, total_count, search_results],
                )
                next_btn.click(
                    lambda results, page, total: do_search_page(results, page, total, "next"),
                    inputs=[search_results, current_page, total_count],
                    outputs=[preview_table, search_status, search_progress, current_page, total_count, search_results],
                )

                # Save button handlers
                save_all_btn.click(
                    save_all_to_db,
                    inputs=[preview_table, keywords_input, conferences_input, year_input, stars_input],
                    outputs=[save_status],
                )

                save_selected_btn.click(
                    save_selected_to_db,
                    inputs=[preview_table, keywords_input, conferences_input, year_input, stars_input],
                    outputs=[save_status],
                )

            # =================================================================
            # TAB 2: SHOP
            # =================================================================
            with gr.TabItem("Shop", id="shop_tab"):

                # Stats row
                with gr.Row():
                    stat1 = gr.Markdown("**-**\nAvailable")
                    stat2 = gr.Markdown("**-**\nIn Cart")
                    stat3 = gr.Markdown("**-**\nHuggingFace")
                    stat4 = gr.Markdown("**-**\nCloud")
                    refresh_btn = gr.Button("Refresh", variant="primary", scale=0)

                shop_status = gr.Textbox(show_label=False, interactive=False, container=False)

                # Filters
                gr.Markdown("### Filters")
                with gr.Row():
                    shop_search = gr.Textbox(
                        label="Search",
                        placeholder="Search repos...",
                        scale=3
                    )
                    shop_conf_filter = gr.Dropdown(
                        label="Conference",
                        choices=["All"] + CONFERENCE_OPTIONS,
                        value="All",
                        scale=1
                    )
                    shop_source_filter = gr.Dropdown(
                        label="Weight Source",
                        choices=["All", "HF", "Cloud", "Release", "GDrive"],
                        value="All",
                        scale=1
                    )
                    shop_min_stars = gr.Slider(
                        label="Min Stars",
                        minimum=0,
                        maximum=500,
                        value=0,
                        step=25,
                        scale=1
                    )

                # Candidates table
                gr.Markdown("### Available Repos")
                shop_table = gr.Dataframe(
                    headers=["Add", "Repository", "Stars", "Conference", "Source"],
                    datatype=["bool", "markdown", "number", "str", "str"],
                    interactive=True,
                    wrap=True,
                )

                add_cart_btn = gr.Button("Add Selected to Cart", variant="primary")

                # Manual add
                gr.Markdown("### Add Custom URL")
                with gr.Row():
                    manual_url = gr.Textbox(
                        placeholder="https://github.com/owner/repo",
                        show_label=False,
                        scale=4
                    )
                    add_to_cart_manual_btn = gr.Button("Add to Cart", variant="primary", scale=0)
                    add_to_db_btn = gr.Button("Add to DB", variant="secondary", scale=0)

                # Cart section
                gr.Markdown("---")
                gr.HTML("""
                    <div style="display: flex; align-items: center; gap: 12px; margin: 16px 0;">
                        <span style="font-size: 1.5rem;">Cart</span>
                        <h2 style="margin: 0; font-size: 1.5rem; font-weight: 700;">Your Cart</h2>
                    </div>
                """)

                with gr.Row():
                    get_links_btn = gr.Button("Get Links", variant="primary", scale=0)
                    clear_btn = gr.Button("Clear Cart", variant="stop", scale=0)

                cart_links = gr.Textbox(
                    label="GitHub URLs (copy these)",
                    lines=6,
                    interactive=False,
                    elem_classes="links-box"
                )

                # State
                shop_df_state = gr.State(None)

                # Event handlers
                refresh_btn.click(
                    refresh_shop,
                    outputs=[shop_table, stat1, stat2, stat3, stat4, cart_links, shop_status, shop_df_state]
                )

                def on_shop_filter(df, search, conf, source, stars):
                    if df is None:
                        ru_units = get_existing_ru_units(RU_UNITS_PATH)
                        repos = load_search_results_for_shop()
                        status_data = load_candidate_status()
                        cart = set(status_data.get("cart", []))
                        df = build_shop_dataframe(repos, ru_units, cart)
                    return filter_shop_dataframe(df, search, conf, source, stars)

                for inp in [shop_search, shop_conf_filter, shop_source_filter, shop_min_stars]:
                    inp.change(
                        on_shop_filter,
                        inputs=[shop_df_state, shop_search, shop_conf_filter, shop_source_filter, shop_min_stars],
                        outputs=[shop_table]
                    )

                add_cart_btn.click(
                    add_to_cart,
                    inputs=[shop_table],
                    outputs=[shop_status, shop_table, cart_links, shop_df_state]
                )

                add_to_cart_manual_btn.click(
                    add_url_to_cart,
                    inputs=[manual_url],
                    outputs=[shop_status, manual_url, cart_links, shop_table]
                )

                add_to_db_btn.click(
                    add_url_to_db,
                    inputs=[manual_url],
                    outputs=[shop_status, manual_url, shop_table]
                )

                get_links_btn.click(
                    lambda: export_cart_links(load_candidate_status()),
                    outputs=[cart_links]
                )

                clear_btn.click(
                    clear_cart,
                    outputs=[shop_status, shop_table, cart_links, shop_df_state]
                )

            # =================================================================
            # TAB 3: CURATED LISTS
            # =================================================================
            with gr.TabItem("Curated Lists", id="curated_tab"):

                gr.Markdown("""
                ### Curated Awesome Lists

                Manage curated paper lists from GitHub "awesome" repositories.
                These lists provide human-curated collections of ML papers with code.
                """)

                # Stats and sync
                with gr.Row():
                    awesome_stats_table = gr.Dataframe(
                        headers=["Source", "Entries", "With Code", "Last Sync"],
                        datatype=["str", "number", "number", "str"],
                        interactive=False,
                    )

                with gr.Row():
                    sync_btn = gr.Button("Sync All Lists", variant="primary")
                    refresh_stats_btn = gr.Button("Refresh Stats")

                awesome_status = gr.Textbox(label="Status", interactive=False, lines=3)

                gr.Markdown("---")
                gr.Markdown("""
                ### Configuration

                Add or modify awesome lists in `config.yaml`:

                ```yaml
                awesome_lists:
                  - repo: "ChaofWang/Awesome-Super-Resolution"
                    name: "Super Resolution"
                    enabled: true
                ```
                """)

                # Event handlers
                sync_btn.click(
                    sync_awesome_lists,
                    outputs=[awesome_status]
                ).then(
                    get_awesome_stats,
                    outputs=[awesome_stats_table, awesome_status]
                )

                refresh_stats_btn.click(
                    get_awesome_stats,
                    outputs=[awesome_stats_table, awesome_status]
                )

        # Load shop data on start
        app.load(
            refresh_shop,
            outputs=[shop_table, stat1, stat2, stat3, stat4, cart_links, shop_status, shop_df_state]
        )

    return app


def main():
    """Main entry point."""
    import os
    os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"
    app = create_ui()
    app.launch(share=False, server_port=5001, css=CUSTOM_CSS)


if __name__ == "__main__":
    main()
