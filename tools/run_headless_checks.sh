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
xvfb-run -a python3 tools/window_visibility_check.py
xvfb-run -a python3 tools/window_visibility_check.py pfc
xvfb-run -a python3 tools/gui_smoke_check.py
xvfb-run -a python3 tools/header_popup_check.py
xvfb-run -a python3 tools/nested_menu_check.py
xvfb-run -a python3 tools/nested_menu_check.py pfc
xvfb-run -a python3 tools/column_menu_check.py
xvfb-run -a python3 tools/column_menu_check.py pfc
xvfb-run -a python3 tools/context_settings_check.py
xvfb-run -a python3 tools/context_settings_check.py pfc
xvfb-run -a python3 tools/single_panel_check.py
xvfb-run -a python3 tools/single_panel_check.py pfc
xvfb-run -a python3 tools/folder_lines_check.py
xvfb-run -a python3 tools/folder_lines_check.py pfc
xvfb-run -a python3 tools/markdown_preview_check.py
xvfb-run -a python3 tools/markdown_preview_check.py pfc
xvfb-run -a python3 tools/markdown_reading_check.py
xvfb-run -a python3 tools/markdown_reading_check.py pfc
xvfb-run -a python3 tools/cloud_overlay_check.py
xvfb-run -a python3 tools/cloud_overlay_check.py pfc
xvfb-run -a python3 tools/tab_panel_drag_check.py
xvfb-run -a python3 tools/tab_lock_check.py
xvfb-run -a python3 tools/tab_lock_check.py pfc
xvfb-run -a python3 tools/drag_refresh_check.py
xvfb-run -a python3 tools/drag_refresh_check.py pfc
xvfb-run -a python3 tools/search_archive_check.py
xvfb-run -a python3 tools/search_archive_check.py pfc
xvfb-run -a python3 tools/path_navigation_check.py
xvfb-run -a python3 tools/path_navigation_check.py pfc
xvfb-run -a python3 tools/archive_exit_check.py
xvfb-run -a python3 tools/archive_exit_check.py pfc
xvfb-run -a python3 tools/zoom_check.py
xvfb-run -a python3 tools/zoom_check.py pfc
xvfb-run -a python3 tools/pathbar_check.py
xvfb-run -a python3 tools/pathbar_check.py pfc
xvfb-run -a python3 tools/pathbar_resume_check.py
xvfb-run -a python3 tools/pathbar_resume_check.py pfc
xvfb-run -a python3 tools/homeprefix_check.py
xvfb-run -a python3 tools/homeprefix_check.py pfc
xvfb-run -a python3 tools/home_icon_check.py
xvfb-run -a python3 tools/home_icon_check.py pfc
xvfb-run -a python3 tools/marquee_check.py
xvfb-run -a python3 tools/marquee_check.py pfc
xvfb-run -a python3 tools/size_column_check.py
xvfb-run -a python3 tools/size_column_check.py pfc
xvfb-run -a python3 tools/vcs_gui_check.py "$project_root"

echo "All headless checks passed."
