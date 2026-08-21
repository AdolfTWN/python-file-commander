#!/usr/bin/env sh
# Run the complete non-interactive validation suite on a Linux CI or server host.
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_root"

command -v xvfb-run >/dev/null 2>&1 || {
    echo "xvfb-run is required; install the xvfb package first." >&2
    exit 1
}

python3 -m unittest discover -s tests -v
xvfb-run -a python3 tools/gui_smoke_check.py
xvfb-run -a python3 tools/header_popup_check.py
xvfb-run -a python3 tools/tab_panel_drag_check.py
xvfb-run -a python3 tools/vcs_gui_check.py "$project_root"

echo "All headless checks passed."
