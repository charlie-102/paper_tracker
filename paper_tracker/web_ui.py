"""
Paper-to-RU Model Shop - Beautiful UI for browsing ML paper repos.

Usage:
    python -m paper_tracker.web_ui
    ./run_web_ui.sh --reload  # Hot reload mode
"""

import gradio as gr
import pandas as pd
from datetime import datetime

try:
    from .ru_sync import (
        get_existing_ru_units,
        load_tracker_results,
        sync_candidates,
        load_candidate_status,
        save_candidate_status,
        export_cart_links,
        add_manual_repo,
        RU_UNITS_PATH,
    )
except ImportError:
    from ru_sync import (
        get_existing_ru_units,
        load_tracker_results,
        sync_candidates,
        load_candidate_status,
        save_candidate_status,
        export_cart_links,
        add_manual_repo,
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

.header-subtitle {
    color: var(--gray-600) !important;
    font-size: 1.1rem !important;
}

/* Stats cards */
.stat-card {
    background: white;
    border: 1px solid var(--gray-200);
    border-radius: 12px;
    padding: 16px 20px;
    text-align: center;
}

.stat-number {
    font-size: 2rem;
    font-weight: 700;
    color: var(--primary);
}

.stat-label {
    font-size: 0.875rem;
    color: var(--gray-600);
    text-transform: uppercase;
    letter-spacing: 0.05em;
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

/* Cart section */
.cart-section {
    background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
    border-radius: 16px;
    padding: 20px;
    margin-top: 24px;
}

.cart-header {
    display: flex;
    align-items: center;
    gap: 8px;
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

/* Badge styles */
.badge {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 600;
}

.badge-hf { background: #fef3c7; color: #92400e; }
.badge-cloud { background: #dbeafe; color: #1e40af; }
.badge-cvpr { background: #dcfce7; color: #166534; }
"""


def get_stats(status_data: dict) -> tuple:
    """Get statistics for display."""
    candidates = status_data.get("candidates", {})
    cart = status_data.get("cart", [])

    total = len(candidates)
    in_cart = len(cart)
    available = total - in_cart

    # Count by source
    hf_count = sum(1 for c in candidates.values() if c.get("weight_source") == "HF")
    cloud_count = sum(1 for c in candidates.values() if c.get("weight_source") == "Cloud")

    return total, available, in_cart, hf_count, cloud_count


def build_candidates_dataframe(status_data: dict) -> pd.DataFrame:
    """Build DataFrame for candidates not in cart."""
    candidates = status_data.get("candidates", {})
    cart = set(status_data.get("cart", []))

    rows = []
    for full_name, info in candidates.items():
        if full_name in cart:
            continue

        conf = info.get("conference", "")
        year = info.get("conference_year", "")
        if conf and year:
            conf_display = f"{conf}'{year[-2:]}" if len(year) >= 2 else conf
        elif conf:
            conf_display = conf
        else:
            conf_display = "-"

        repo_name = info.get("name", full_name.split("/")[-1])
        repo_url = info.get("url", f"https://github.com/{full_name}")
        repo_link = f"[{repo_name}]({repo_url})"

        rows.append({
            "Add": False,
            "Repository": repo_link,
            "Stars": info.get("stars", 0),
            "Conference": conf_display,
            "Source": info.get("weight_source", "-") or "-",
            "full_name": full_name,
        })

    df = pd.DataFrame(rows)
    if len(df) > 0:
        df = df.sort_values("Stars", ascending=False).reset_index(drop=True)

    return df


def filter_dataframe(df: pd.DataFrame, search: str, conference: str, source: str, min_stars: int) -> pd.DataFrame:
    """Filter the candidates dataframe."""
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


def refresh_all():
    """Refresh data and return all UI components."""
    ru_units = get_existing_ru_units(RU_UNITS_PATH)
    repos = load_tracker_results()
    status_data = sync_candidates(repos, ru_units)
    save_candidate_status(status_data)

    df = build_candidates_dataframe(status_data)
    total, available, in_cart, hf_count, cloud_count = get_stats(status_data)
    links = export_cart_links(status_data)

    status = f"Synced {total} repos ({len(ru_units)} RU units excluded)"

    return (
        df,  # table
        f"**{total}**\nTotal Repos",  # stat1
        f"**{available}**\nAvailable",  # stat2
        f"**{in_cart}**\nIn Cart",  # stat3
        f"**{hf_count}**\nHuggingFace",  # stat4
        f"**{cloud_count}**\nCloud",  # stat5
        links,  # cart links
        status,  # status message
        df,  # state
    )


def add_to_cart(df: pd.DataFrame):
    """Add selected repos to cart."""
    if df is None or len(df) == 0:
        status_data = load_candidate_status()
        return "No repos available", df, export_cart_links(status_data), df

    status_data = load_candidate_status()
    cart = set(status_data.get("cart", []))
    candidates = status_data.get("candidates", {})

    selected = df[df["Add"] == True]
    if len(selected) == 0:
        return "Select repos first", df, export_cart_links(status_data), df

    added = 0
    for _, row in selected.iterrows():
        full_name = row["full_name"]
        if full_name not in cart:
            cart.add(full_name)
            if full_name in candidates:
                candidates[full_name]["status"] = "confirmed"
                candidates[full_name]["reviewed_at"] = datetime.now().isoformat()
            added += 1

    status_data["cart"] = list(cart)
    status_data["candidates"] = candidates
    save_candidate_status(status_data)

    new_df = build_candidates_dataframe(status_data)
    return f"Added {added} repos to cart", new_df, export_cart_links(status_data), new_df


def add_url_to_cart(url: str):
    """Add URL directly to cart."""
    if not url or not url.strip():
        return "Enter a URL", url, gr.update(), gr.update()

    status_data = load_candidate_status()
    success, msg = add_manual_repo(url.strip(), status_data)

    if success:
        full_name = url.strip().replace("https://github.com/", "").rstrip("/")
        cart = set(status_data.get("cart", []))
        cart.add(full_name)
        status_data["cart"] = list(cart)
        if full_name in status_data.get("candidates", {}):
            status_data["candidates"][full_name]["status"] = "confirmed"
        save_candidate_status(status_data)

        df = build_candidates_dataframe(status_data)
        return f"Added: {full_name}", "", export_cart_links(status_data), df

    return msg, url, gr.update(), gr.update()


def add_url_to_db(url: str):
    """Add URL to candidates database."""
    if not url or not url.strip():
        return "Enter a URL", url, gr.update()

    status_data = load_candidate_status()
    success, msg = add_manual_repo(url.strip(), status_data)

    if success:
        save_candidate_status(status_data)
        df = build_candidates_dataframe(status_data)
        return msg, "", df

    return msg, url, gr.update()


def clear_cart():
    """Clear cart."""
    status_data = load_candidate_status()

    for full_name in status_data.get("cart", []):
        if full_name in status_data.get("candidates", {}):
            status_data["candidates"][full_name]["status"] = "new"

    status_data["cart"] = []
    save_candidate_status(status_data)

    df = build_candidates_dataframe(status_data)
    return "Cart cleared", df, "", df


def create_ui():
    """Create the beautiful shopping UI."""

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
                    Browse and collect ML paper repos with pretrained weights
                </p>
            </div>
        """)

        # Stats row
        with gr.Row():
            stat1 = gr.Markdown("**-**\nTotal Repos")
            stat2 = gr.Markdown("**-**\nAvailable")
            stat3 = gr.Markdown("**-**\nIn Cart")
            stat4 = gr.Markdown("**-**\nHuggingFace")
            stat5 = gr.Markdown("**-**\nCloud")
            refresh_btn = gr.Button("Refresh", variant="primary", scale=0)

        status_msg = gr.Textbox(show_label=False, interactive=False, container=False)

        # Filters
        gr.Markdown("### Filters")
        with gr.Row():
            search_box = gr.Textbox(
                label="Search",
                placeholder="Search repos...",
                scale=3
            )
            conf_filter = gr.Dropdown(
                label="Conference",
                choices=["All", "CVPR", "ECCV", "ICCV", "NeurIPS", "ICML", "ICLR", "MICCAI", "TPAMI"],
                value="All",
                scale=1
            )
            source_filter = gr.Dropdown(
                label="Weight Source",
                choices=["All", "HF", "Cloud", "Release"],
                value="All",
                scale=1
            )
            min_stars = gr.Slider(
                label="Min Stars",
                minimum=0,
                maximum=500,
                value=0,
                step=25,
                scale=1
            )

        # Candidates table
        gr.Markdown("### Available Repos")
        candidates_table = gr.Dataframe(
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
                <span style="font-size: 1.5rem;">🛒</span>
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
        df_state = gr.State(None)

        # Event handlers
        refresh_btn.click(
            refresh_all,
            outputs=[candidates_table, stat1, stat2, stat3, stat4, stat5, cart_links, status_msg, df_state]
        )

        def on_filter(df, search, conf, source, stars):
            if df is None:
                status_data = load_candidate_status()
                df = build_candidates_dataframe(status_data)
            return filter_dataframe(df, search, conf, source, stars)

        for inp in [search_box, conf_filter, source_filter, min_stars]:
            inp.change(
                on_filter,
                inputs=[df_state, search_box, conf_filter, source_filter, min_stars],
                outputs=[candidates_table]
            )

        add_cart_btn.click(
            add_to_cart,
            inputs=[candidates_table],
            outputs=[status_msg, candidates_table, cart_links, df_state]
        )

        add_to_cart_manual_btn.click(
            add_url_to_cart,
            inputs=[manual_url],
            outputs=[status_msg, manual_url, cart_links, candidates_table]
        )

        add_to_db_btn.click(
            add_url_to_db,
            inputs=[manual_url],
            outputs=[status_msg, manual_url, candidates_table]
        )

        get_links_btn.click(
            lambda: export_cart_links(load_candidate_status()),
            outputs=[cart_links]
        )

        clear_btn.click(
            clear_cart,
            outputs=[status_msg, candidates_table, cart_links, df_state]
        )

        # Load on start
        app.load(
            refresh_all,
            outputs=[candidates_table, stat1, stat2, stat3, stat4, stat5, cart_links, status_msg, df_state]
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
