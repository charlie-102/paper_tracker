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

def apply_template(template_name: str):
    """Apply a search template to populate fields."""
    if template_name not in SEARCH_TEMPLATES:
        return gr.update(), gr.update(), gr.update(), gr.update()

    template = SEARCH_TEMPLATES[template_name]
    return (
        template.get("keywords", ""),
        template.get("conferences", []),
        template.get("year", "2024"),
        template.get("weights", "Has Weights"),
    )


def do_search(keywords_str: str, conferences: list, year: str, weights: str, min_stars: int):
    """Execute GitHub search and return preview results."""
    if not keywords_str.strip():
        return pd.DataFrame(), "Enter keywords to search"

    # Parse keywords
    keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]

    # Map weight filter
    weight_map = {
        "Has Weights": "has_weights",
        "No Weights": "no_weights",
        "All": "all"
    }
    weight_filter = weight_map.get(weights, "has_weights")

    # Conference year
    conf_year = None if year == "Any" else year

    try:
        searcher = GitHubSearcher()
        results = searcher.search(
            keywords=keywords,
            conferences=conferences or [],
            conference_year=conf_year,
            weight_filter=weight_filter,
            min_stars=min_stars,
            max_results_per_keyword=30,
        )

        if not results:
            return pd.DataFrame(), "No repos found matching criteria"

        # Build dataframe for preview
        rows = []
        for repo in results:
            conf_display = repo.get("conference", "")
            if conf_display and repo.get("conference_year"):
                conf_display = f"{conf_display}'{repo['conference_year'][-2:]}"

            rows.append({
                "Select": False,
                "Repository": f"[{repo['name']}]({repo['url']})",
                "Stars": repo.get("stars", 0),
                "Conference": conf_display or "-",
                "Weights": repo.get("weight_status", "-") or "-",
                "full_name": repo["full_name"],
            })

        df = pd.DataFrame(rows)
        status = f"Found {len(results)} repos (preview - not saved yet)"
        return df, status

    except Exception as e:
        return pd.DataFrame(), f"Search error: {str(e)}"


def save_all_to_db(preview_df: pd.DataFrame, keywords_str: str, conferences: list, year: str, weights: str, min_stars: int):
    """Save all preview results to search_results.json."""
    if preview_df is None or len(preview_df) == 0:
        return "No results to save"

    # Get the full search results (need to re-run or cache)
    keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]
    weight_map = {"Has Weights": "has_weights", "No Weights": "no_weights", "All": "all"}

    try:
        searcher = GitHubSearcher()
        results = searcher.search(
            keywords=keywords,
            conferences=conferences or [],
            conference_year=None if year == "Any" else year,
            weight_filter=weight_map.get(weights, "has_weights"),
            min_stars=min_stars,
            max_results_per_keyword=30,
        )

        query_info = {
            "keywords": keywords,
            "conferences": conferences,
            "conference_year": year,
            "weight_filter": weights,
            "min_stars": min_stars,
        }

        save_search_results(results, query_info)
        return f"Saved {len(results)} repos to database"

    except Exception as e:
        return f"Error saving: {str(e)}"


def save_selected_to_db(preview_df: pd.DataFrame, keywords_str: str, conferences: list, year: str, weights: str, min_stars: int):
    """Save only selected repos to search_results.json."""
    if preview_df is None or len(preview_df) == 0:
        return "No results to save"

    selected = preview_df[preview_df["Select"] == True]
    if len(selected) == 0:
        return "No repos selected"

    # Get full names of selected repos
    selected_names = set(selected["full_name"].tolist())

    # Re-run search to get full data
    keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]
    weight_map = {"Has Weights": "has_weights", "No Weights": "no_weights", "All": "all"}

    try:
        searcher = GitHubSearcher()
        all_results = searcher.search(
            keywords=keywords,
            conferences=conferences or [],
            conference_year=None if year == "Any" else year,
            weight_filter=weight_map.get(weights, "has_weights"),
            min_stars=min_stars,
            max_results_per_keyword=30,
        )

        # Filter to selected only
        selected_results = [r for r in all_results if r["full_name"] in selected_names]

        query_info = {
            "keywords": keywords,
            "conferences": conferences,
            "conference_year": year,
            "weight_filter": weights,
            "min_stars": min_stars,
            "selection": "manual",
        }

        save_search_results(selected_results, query_info)
        return f"Saved {len(selected_results)} selected repos to database"

    except Exception as e:
        return f"Error saving: {str(e)}"


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

                gr.Markdown("### Quick Templates")
                with gr.Row():
                    template_btns = {}
                    for name in SEARCH_TEMPLATES:
                        template_btns[name] = gr.Button(name, size="sm", elem_classes="template-btn")

                gr.Markdown("### Search Parameters")

                keywords_input = gr.Textbox(
                    label="Keywords (comma-separated)",
                    placeholder="image restoration, super resolution, denoising",
                    lines=1,
                )

                conferences_input = gr.CheckboxGroup(
                    choices=CONFERENCE_OPTIONS,
                    label="Filter by Conference (empty = all)",
                    value=[],
                )

                with gr.Row():
                    year_input = gr.Dropdown(
                        choices=["Any", "2024", "2025", "2026"],
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
                    weights_input = gr.Radio(
                        choices=["Has Weights", "All", "No Weights"],
                        value="Has Weights",
                        label="Weight Filter",
                    )

                search_btn = gr.Button("Search GitHub", variant="primary")

                # Preview section
                gr.Markdown("### Preview Results")
                search_status = gr.Markdown("*Click Search to find repos*")

                preview_table = gr.Dataframe(
                    headers=["Select", "Repository", "Stars", "Conference", "Weights"],
                    datatype=["bool", "markdown", "number", "str", "str"],
                    interactive=True,
                    wrap=True,
                )

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

                # Template button handlers
                for name, btn in template_btns.items():
                    btn.click(
                        lambda n=name: apply_template(n),
                        outputs=[keywords_input, conferences_input, year_input, weights_input],
                    )

                # Search button handler
                search_btn.click(
                    do_search,
                    inputs=[keywords_input, conferences_input, year_input, weights_input, stars_input],
                    outputs=[preview_table, search_status],
                )

                # Save button handlers
                save_all_btn.click(
                    save_all_to_db,
                    inputs=[preview_table, keywords_input, conferences_input, year_input, weights_input, stars_input],
                    outputs=[save_status],
                )

                save_selected_btn.click(
                    save_selected_to_db,
                    inputs=[preview_table, keywords_input, conferences_input, year_input, weights_input, stars_input],
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
