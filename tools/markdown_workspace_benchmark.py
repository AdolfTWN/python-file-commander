"""Synthetic local-storage scan budget check, not a OneDrive/network benchmark."""
import json
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pycommander.mdworkspace import scan_markdown_workspace
from pycommander.preview import markdown_document, decode_text

with tempfile.TemporaryDirectory(prefix='pfc-md-budget-') as raw:
    root=Path(raw);document=root/'Notes.md';document.write_text('# Notes',encoding='utf-8')
    for number in range(5500):
        (root/f'item-{number:04d}.txt').touch()
    started=time.monotonic()
    result=scan_markdown_workspace(dict(root=str(root),path=str(document),depth=3,
                                        mode='files',query='absent'),markdown_document,decode_text)
    elapsed=time.monotonic()-started
    assert result['visited']<=5000
    assert 'entries' in result['reasons'] or 'time' in result['reasons'],result
    print(json.dumps(dict(fixture='5501 local entries, missing filename',seconds=round(elapsed,4),
                          visited=result['visited'],reasons=result['reasons'])))
