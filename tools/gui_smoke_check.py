"""Non-destructive smoke check for the generated portable GUI."""

import tempfile
from pathlib import Path
import sys
import configparser

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pfc


def main() -> None:
    original = pfc.Commander._find_ini_path
    with tempfile.TemporaryDirectory() as raw:
        ini_path = Path(raw) / "pfc.ini"
        pfc.Commander._find_ini_path = staticmethod(lambda: ini_path)
        app = None
        try:
            app = pfc.Commander(); app.withdraw(); app.update_idletasks(); app.update()
            labels = [app.files_menu.entrycget(index, "label")
                      for index in range(app.files_menu.index("end") + 1)
                      if app.files_menu.type(index) not in {"separator", "tearoff"}]
            required = {"Copy to Clipboard\tCtrl+C", "Paste\tCtrl+V", "Delete\tDel",
                        "Permanent Delete\tShift+Del", "Send Delete to Recycle Bin",
                        "Continue After File Errors", "Favorites", "Recent Folders"}
            assert required.issubset(labels), required.difference(labels)
            assert app.recycle_bin_var.get() and app.continue_errors_var.get()
            assert ini_path.exists(), "pfc.ini was not generated on first launch"
            app.toggle_favorite()
            assert app.favorites, "Favorite folder was not stored"
            saved = configparser.ConfigParser(); saved.read(ini_path, encoding="utf-8")
            assert saved.getboolean("operations", "send_delete_to_recycle_bin")
            assert saved.get("hotkeys", "permanent_delete") == "<Shift-Delete>"
            assert saved.get("navigation", "favorites") != "[]"
            print("GUI smoke check passed")
        finally:
            if app is not None:
                app.destroy()
            pfc.Commander._find_ini_path = original


if __name__ == "__main__":
    main()
