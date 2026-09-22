"""Build the portable single-file edition from the maintainable package sources."""

from datetime import datetime
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def build() -> Path:
    i18n = (ROOT / "pycommander" / "i18n.py").read_text(encoding="utf-8")
    fileops = (ROOT / "pycommander" / "fileops.py").read_text(encoding="utf-8")
    clipboard = (ROOT / "pycommander" / "clipboard.py").read_text(encoding="utf-8")
    icons = (ROOT / "pycommander" / "icons.py").read_text(encoding="utf-8")
    startup = (ROOT / "pycommander" / "startup.py").read_text(encoding="utf-8")
    dirwatch = (ROOT / "pycommander" / "dirwatch.py").read_text(encoding="utf-8")
    vcs = (ROOT / "pycommander" / "vcs.py").read_text(encoding="utf-8")
    tabs = (ROOT / "pycommander" / "tabs.py").read_text(encoding="utf-8")
    tooltip = (ROOT / "pycommander" / "tooltip.py").read_text(encoding="utf-8")
    pathbar = (ROOT / "pycommander" / "pathbar.py").read_text(encoding="utf-8")
    homeprefix = (ROOT / "pycommander" / "homeprefix.py").read_text(encoding="utf-8")
    homeprefix = homeprefix.replace("from __future__ import annotations\n", "", 1)
    homeprefix = "\n".join(line for line in homeprefix.splitlines() if not line.startswith("from .")) + "\n"
    compare = (ROOT / "pycommander" / "compare.py").read_text(encoding="utf-8")
    preview = (ROOT / "pycommander" / "preview.py").read_text(encoding="utf-8")
    search = (ROOT / "pycommander" / "search.py").read_text(encoding="utf-8")
    multirename = (ROOT / "pycommander" / "multirename.py").read_text(encoding="utf-8")
    archivefs = (ROOT / "pycommander" / "archivefs.py").read_text(encoding="utf-8")
    spaceanalyzer = (ROOT / "pycommander" / "spaceanalyzer.py").read_text(encoding="utf-8")
    shelldnd = (ROOT / "pycommander" / "shelldnd.py").read_text(encoding="utf-8")
    shellmenu = (ROOT / "pycommander" / "shellmenu.py").read_text(encoding="utf-8")
    app = (ROOT / "pycommander" / "app.py").read_text(encoding="utf-8")
    package = (ROOT / "pycommander" / "__init__.py").read_text(encoding="utf-8")
    version_match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', package, re.MULTILINE)
    if version_match is None:
        raise RuntimeError("pycommander.__version__ is missing")
    app = app.replace("from . import __version__\n", f'__version__ = "{version_match.group(1)}"\n', 1)
    build_date = datetime.now().strftime("%Y/%m/%d")
    app = app.replace('BUILD_DATE = datetime.now().strftime("%Y/%m/%d")',
                      f'BUILD_DATE = "{build_date}"', 1)

    i18n = i18n.replace("from __future__ import annotations\n\n", "", 1)
    fileops = fileops.replace("from __future__ import annotations\n\n", "", 1)
    clipboard = clipboard.replace("from __future__ import annotations\n\n", "", 1)
    icons = icons.replace("from __future__ import annotations\n\n", "", 1)
    startup = startup.replace("from __future__ import annotations\n\n", "", 1)
    dirwatch = dirwatch.replace("from __future__ import annotations\n\n", "", 1)
    vcs = vcs.replace("from __future__ import annotations\n\n", "", 1)
    tabs = tabs.replace("from __future__ import annotations\n\n", "", 1)
    tabs = "\n".join(line for line in tabs.splitlines() if not line.startswith("from .")) + "\n"
    tabicons = (ROOT / "pycommander" / "tabicons.py").read_text(encoding="utf-8")
    tabs = "\n".join(line for line in tabicons.splitlines() if not line.startswith("from .")) + "\n\n" + tabs
    tooltip = tooltip.replace("from __future__ import annotations\n\n", "", 1)
    pathbar = pathbar.replace("from __future__ import annotations\n", "", 1)
    pathbar = "\n".join(line for line in pathbar.splitlines() if not line.startswith("from .")) + "\n"
    tooltip += "\n\n" + (ROOT / "pycommander" / "columnsettings.py").read_text(encoding="utf-8")
    tooltip += "\n\n" + pathbar
    tooltip += "\n\n" + homeprefix
    tooltip += "\n\n" + (ROOT / "pycommander" / "cloudstatus.py").read_text(encoding="utf-8")
    tooltip += "\n\n" + (ROOT / "pycommander" / "marquee.py").read_text(encoding="utf-8")
    detailcells = (ROOT / "pycommander" / "detailcells.py").read_text(encoding="utf-8")
    tooltip += "\n\n" + "\n".join(line for line in detailcells.splitlines() if not line.startswith("from ."))
    singlepanel = (ROOT / 'pycommander' / 'singlepanel.py').read_text(encoding='utf-8')
    tooltip += '\n\n' + '\n'.join(line for line in singlepanel.splitlines() if not line.startswith('from .'))
    tooltip += '\n\n' + (ROOT / 'pycommander' / 'windowplacement.py').read_text(encoding='utf-8')
    tooltip += '\n\n' + (ROOT / 'pycommander' / 'settingsshots.py').read_text(encoding='utf-8')
    settings = (ROOT / 'pycommander' / 'settings.py').read_text(encoding='utf-8')
    tooltip += '\n\n' + '\n'.join(line for line in settings.splitlines() if not line.startswith('from .'))
    compare = compare.replace("from __future__ import annotations\n\n", "", 1)
    compare = "\n".join(line for line in compare.splitlines() if not line.startswith("from .")) + "\n"
    preview = preview.replace("from __future__ import annotations\n\n", "", 1)
    preview = "\n".join(line for line in preview.splitlines() if not line.startswith("from .")) + "\n"
    preview = (ROOT / 'pycommander' / 'markdownblocks.py').read_text(encoding='utf-8') + '\n\n' + preview
    preview = (ROOT/'pycommander'/'mdlinks.py').read_text(encoding='utf-8')+'\n\n'+(ROOT/'pycommander'/'mdjobs.py').read_text(encoding='utf-8')+'\n\n'+preview
    search = search.replace("from __future__ import annotations\n\n", "", 1)
    search = "\n".join(line for line in search.splitlines() if not line.startswith("from .")) + "\n"
    multirename = multirename.replace("from __future__ import annotations\n\n", "", 1)
    multirename = "\n".join(line for line in multirename.splitlines() if not line.startswith("from .")) + "\n"
    archivefs = archivefs.replace("from __future__ import annotations\n\n", "", 1)
    spaceanalyzer = spaceanalyzer.replace("from __future__ import annotations\n\n", "", 1)
    spaceanalyzer = "\n".join(
        line for line in spaceanalyzer.splitlines() if not line.startswith("from .")) + "\n"
    shelldnd = shelldnd.replace("from __future__ import annotations\n\n", "", 1)
    shelldnd = "\n".join(line for line in shelldnd.splitlines() if not line.startswith("from .")) + "\n"
    shellmenu = shellmenu.replace("from __future__ import annotations\n\n", "", 1)
    app = app.replace("from __future__ import annotations\n\n", "", 1)
    app = "\n".join(line for line in app.splitlines() if not line.startswith("from .")) + "\n"
    banner = '''"""Portable Python File Commander.

Generated from the pycommander package. Requires only Python 3.10+ with Tk.
Do not edit this file directly; run tools/build_single_file.py after source changes.
"""

from __future__ import annotations

'''
    output = ROOT / "pfc.py"
    output.write_text(banner + i18n + "\n\n" + fileops + "\n\n" + clipboard + "\n\n" + icons + "\n\n" + startup + "\n\n" + dirwatch + "\n\n" + vcs + "\n\n" + tabs + "\n\n" + tooltip + "\n\n" + compare + "\n\n" + preview + "\n\n" + search + "\n\n" + multirename + "\n\n" + archivefs + "\n\n" + spaceanalyzer + "\n\n" + shelldnd + "\n\n" + shellmenu + "\n\n" + app + "\n\nif __name__ == \"__main__\":\n    main()\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    print(build())
