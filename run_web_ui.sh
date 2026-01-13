#!/bin/bash
# Launch the Paper-to-RU web UI
# Usage:
#   ./run_web_ui.sh          # Normal mode
#   ./run_web_ui.sh --reload # Hot reload mode (auto-refresh on code changes)

# Activate conda environment
source ~/miniconda3/etc/profile.d/conda.sh
conda activate lerobot

# Change to project directory
cd "$(dirname "$0")"

# Disable Gradio analytics
export GRADIO_ANALYTICS_ENABLED=False
export no_proxy="*"
export NO_PROXY="*"

if [ "$1" == "--reload" ]; then
    echo "Starting with hot reload enabled..."
    cd paper_tracker
    export GRADIO_SERVER_PORT=5001
    gradio web_ui.py --demo-name create_ui
else
    python -m paper_tracker.web_ui
fi
