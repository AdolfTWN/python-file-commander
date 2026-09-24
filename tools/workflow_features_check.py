"""Source/portable UI regressions for safe editing and compact workflow features."""
import importlib
from pathlib import Path
import sys
import tempfile
import time
import threading
import zipfile
from unittest import mock
from tkinter import simpledialog

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
module = sys.argv[1] if len(sys.argv) > 1 else 'pycommander.app'
pfc = importlib.import_module(module)
work = pfc if module == 'pfc' else importlib.import_module('pycommander.workspaces')
data = pfc if module == 'pfc' else importlib.import_module('pycommander.workflowdata')


def settle(app, seconds=.1):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.update(); time.sleep(.005)


def until(app, predicate, seconds=6):
    end = time.monotonic() + seconds
    while not predicate():
        assert time.monotonic() < end, 'Timed out'
        settle(app, .03)


with tempfile.TemporaryDirectory(prefix='pfc-workflows-check-') as raw:
    root = Path(raw)
    left, right = root/'left', root/'right'; left.mkdir(); right.mkdir()
    for directory in (left, right):
        (directory/'docs').mkdir(); (directory/'docs/node_modules').mkdir()
        (directory/'docs/node_modules/internal.js').write_text('never copy')
    a, b = left/'note.txt', right/'note.txt'
    a.write_bytes(b'\xef\xbb\xbfversion 1\r\nkeep\r\n')
    b.write_bytes(b'version 2\nkeep\n')
    md = left/'Guide.md'; linked = left/'Linked.md'
    md.write_text('# Intro\n\n' + ('Paragraph with useful content.\n\n'*70) + '# Work\n\nTarget\n', encoding='utf-8')
    linked.write_text('# Linked\n\nNew document\n', encoding='utf-8')
    pfc.Commander._find_ini_path = staticmethod(lambda: root/'pfc.ini')
    pfc.Commander._sync_auto_start = lambda *a, **kw: True
    pfc.Commander._start_windows_tray = lambda *a: None
    app = pfc.Commander(); errors = []
    app.report_callback_exception = lambda *exc: errors.append(str(exc))
    try:
        app.auto_font_size_var.set(False); app.geometry('1400x900+0+0')
        app.font_size_var.set('small'); app.apply_font_size(save=False)
        for tabs in app.panel_tabs: tabs.current().navigate(left)
        app.active = app.left_tabs.current(); app.active.focus_file_list(); settle(app)
        app.compare_paths(a, b); settle(app)
        cw = app.compare_window; frame = cw.current_comparison()
        assert frame.view.left.cget('state') == 'disabled'
        assert frame.view.left.tag_ranges('inline_diff'), 'actual changed digits are highlighted'
        assert 'CRLF' in frame.document_controls['Left'][1].cget('text')
        frame.edit('Left'); settle(app)
        editor = app.grab_current(); assert editor.document.path == a
        editor.text.delete('1.0', 'end'); editor.text.insert('1.0', 'version 3\n\nkeep\n')
        editor.save(); settle(app)
        assert a.read_bytes() == b'\xef\xbb\xbfversion 3\r\n\r\nkeep\r\n'
        assert cw.current_comparison() is frame, 'saving does not destroy/rebuild the tab'
        editor.text.insert('end', 'unsaved')
        a.write_bytes(b'\xef\xbb\xbfexternal\r\n')
        cw._auto_refresh(); settle(app)
        assert 'unsaved' in editor.text.get('1.0','end')
        with mock.patch.object(pfc.messagebox, 'showerror') as error:
            editor.save(); assert error.called
        with mock.patch.object(pfc.messagebox, 'askyesnocancel', return_value=None):
            cw.close(); assert cw.winfo_exists() and editor.winfo_exists()
        with mock.patch.object(pfc.messagebox, 'askyesnocancel', return_value=False): editor.close()
        frame.reload_content(); assert 'external' in frame.view.left.get('1.0','end')
        cw.close(); app.compare_window = None

        app.font_size_var.set('large'); app.apply_font_size(save=False)
        app.show_saved_comparisons(); settle(app)
        empty = app.compare_window
        assert empty.scale == app._font_scales['large']
        assert app.grab_current().save_button.instate(['disabled'])
        app.grab_current().close()
        empty._navigate('next'); empty.focus_search()  # Empty sessions are inert.
        empty.close(); app.compare_window = None
        app.font_size_var.set('small'); app.apply_font_size(save=False)

        # Archive previews must not offer edits to disposable extracted files.
        archive = root/'archive.zip'
        with zipfile.ZipFile(archive, 'w') as zipped: zipped.write(a, a.name)
        app.compare_paths(archive, right); cw = app.compare_window; fc = cw.current_comparison()
        until(app, lambda: not fc._scanning)
        fc.open_nested_detail(fc.left_root/a.name, b, a.name)
        detail = next(iter(fc.nested_details.values()))['detail']
        assert detail.document_controls['Left'][0].instate(['disabled'])
        assert detail.document_controls['Right'][0].instate(['!disabled'])
        detail.edit('Left'); assert not getattr(cw, '_editors', None)
        cw.close(); app.compare_window = None

        app.compare_paths(left, right); cw = app.compare_window; fc = cw.current_comparison()
        until(app, lambda: not fc._scanning)
        assert not any('node_modules' in name for status,name,*_ in fc.rows)
        iid=next(i for i, paths in fc.item_paths.items() if paths[0] == a)
        fc._select_items((iid,)); before_items=tuple(fc._all_tree_items())
        with mock.patch.object(fc,'populate',side_effect=AssertionError('Direction must not rebuild rows')):
            fc.set_action('right')
        assert tuple(fc._all_tree_items())==before_items and fc.left_tree.set(iid,'action')=='→'
        fc.exclude_var.set('*.md'); fc.start_scan(); until(app, lambda: not fc._scanning)
        saved = cw.capture_session(); assert saved['rules']['excludes'] == '*.md'
        data.WorkflowRecords(app.config_data,'compare_sessions').put('Reports', saved)
        cw.open_session(saved); new = cw.current_comparison(); until(app, lambda: not new._scanning)
        assert new.exclude_var.get() == '*.md' and not new.actions
        report = root/'report.html'
        with mock.patch.object(pfc.filedialog,'asksaveasfilename',return_value=str(report)):
            new.export_report()
        assert 'PFC comparison report' in report.read_text() and str(root) not in report.read_text()
        original_source=a.read_bytes()
        with mock.patch.object(pfc.filedialog,'asksaveasfilename',return_value=str(a)), \
             mock.patch.object(pfc.messagebox,'showerror') as error:
            new.export_report(); assert error.called
        assert a.read_bytes()==original_source
        cw.saved_comparisons(); settle(app); picker = app.grab_current()
        assert picker.entries[0]['name'] == 'Reports'
        def cancel_name(*args, **kwargs):
            picker.grab_release(); return None
        with mock.patch.object(simpledialog,'askstring',side_effect=cancel_name):
            picker.save_current()
        assert app.grab_current() is picker
        picker.close()
        cw.close(); app.compare_window = None

        # File-copy work runs off Tk, conflicts stay on Tk, and cancellation is
        # explicit at a file boundary. Timer ticks prove the UI keeps dispatching.
        syncmod = pfc if module == 'pfc' else importlib.import_module('pycommander.syncprogress')
        destination = root/'sync'; destination.mkdir()
        (destination/a.name).write_text('conflict')
        threads = []; ticks = []
        def resolver(source,target):
            threads.append(threading.current_thread()); return 'replace'
        original_copy = syncmod.copy_items
        def slow_copy(*args,**kwargs):
            time.sleep(.12); return original_copy(*args,**kwargs)
        app.after(30,lambda:ticks.append('alive'))
        with mock.patch.object(syncmod,'copy_items',side_effect=slow_copy), \
             mock.patch.object(app,'_conflict_resolver',return_value=resolver):
            result = app.execute_sync_plans([(a,destination/a.name)])
        assert result.completed == [a] and ticks
        assert threads and all(t is threading.main_thread() for t in threads)
        assert (destination/a.name).read_bytes() == a.read_bytes()
        sources = []
        for index in range(8):
            path = left/f'copy-{index}.txt';path.write_text('copy');sources.append(path)
        app.after(100,lambda:app._sync_dialog.cancel())
        with mock.patch.object(syncmod,'copy_items',side_effect=slow_copy), \
             mock.patch.object(app,'_show_operation_result'):
            result = app.execute_sync_plans([(path,destination/path.name) for path in sources])
        assert result.skipped and len(result.completed) < len(sources)

        # Commands resolve without reading files; Enter returns focus before execution.
        app.active.focus_file_list(); app.show_command_palette(); settle(app)
        palette = app.grab_current(); palette.query.set('workspaces'); settle(app)
        assert len(palette.filtered) == 1
        calls = []; app._dispatch_global_hotkey(lambda: calls.append('background'))
        assert not calls
        palette.query.set('no-such-command'); settle(app)
        assert not palette.filtered and 'No matching' in palette.hint.cget('text')
        palette.query.set('font_size'); settle(app)
        assert palette.filtered
        scale = app.font_size_var.get()
        palette.entry.event_generate('<Control-MouseWheel>', delta=120); settle(app)
        assert app.font_size_var.get() == scale
        palette.close()

        # Named workspaces retain per-tab options/locks and both layout modes.
        pane = app.left_tabs.add_tab(right); pane.show_hidden = True
        pane.set_quick_filter('*.txt'); pane.lock_mode = 'locked'; pane.locked_path = right
        pane.tab_group = 'Project notes'
        app.left_tabs.set_lock(pane, 'locked', notify=False)
        app.panel_count_var.set(1); app.apply_panel_count(); settle(app)
        snapshot = work.capture_workspace(app)
        app.panel_count_var.set(2); app.apply_panel_count()
        app.left_tabs.add_tab(left/'docs'); settle(app)
        before = work.capture_workspace(app)
        with mock.patch.object(pfc.messagebox,'askyesno',return_value=True):
            assert work.restore_workspace(app, snapshot)
        settle(app, .3)
        restored = work.capture_workspace(app)
        assert restored['groups'] == snapshot['groups'], (restored,snapshot)
        assert restored['panels'] == 1
        assert data.WorkflowRecords(app.config_data,'workspace_undo').read()[0]['data']['groups'] == before['groups']
        with mock.patch.object(pfc.messagebox,'askyesno',return_value=True): app.restore_previous_workspace()
        settle(app); assert work.capture_workspace(app)['groups'] == before['groups']

        app.preview_window = pfc.PreviewWindow(app, app.config_data, app.save_config, [md, linked], md)
        preview = app.preview_window
        until(app, lambda: preview._md_model.get('rendered') and preview._md_insert is None)
        preview.text.yview_moveto(.55); settle(app)
        bookmark = preview._capture_markdown_position(); assert bookmark['fraction'] > .1
        data.WorkflowRecords(app.config_data,'markdown_bookmarks').put('Working section', bookmark)
        preview.close(); app.preview_window = None
        preview = pfc.PreviewWindow(app, app.config_data, app.save_config, [md,linked], md)
        app.preview_window = preview
        until(app, lambda: preview._md_model.get('rendered') and preview._md_insert is None)
        assert abs(preview.text.yview()[0] - bookmark['fraction']) < .05
        preview.open_markdown_bookmark(dict(bookmark,path=str(linked)))
        until(app, lambda: preview.path == linked and preview._md_insert is None)
        assert preview._md_boundary == left
        preview.markdown_back()
        until(app, lambda: preview.path == md and preview._md_insert is None)
        assert preview._md_boundary == left
        preview.markdown_bookmarks(); settle(app); picker = app.grab_current()
        assert picker.entries[0]['name'] == 'Working section'; picker.close()
        preview.close(); app.preview_window = None
        assert not errors, errors
        print(f'{module}: workflow UI checks passed', flush=True)
    finally:
        if app.winfo_exists():
            with mock.patch.object(pfc.messagebox,'askyesnocancel',return_value=False):
                app.close_app()
