"""Named file-manager layouts, with a reversible pre-switch snapshot."""
from pathlib import Path
from tkinter import messagebox

from .i18n import tr
from .workflowdata import WorkflowRecords
from .workflows import WorkflowPicker


def capture_workspace(app):
    groups = []
    for tabs in app.panel_tabs:
        panes = []
        for pane in tabs.panes():
            panes.append(dict(path=str(pane.persistent_path()), filter=pane.quick_filter_var.get(),
                color=tabs._colors.get(pane, 'default'), lock=pane.lock_mode,
                tab_group=getattr(pane,'tab_group',''),
                locked_path=str(pane.locked_path or pane.persistent_path()),
                sort=pane.sort_column, descending=pane.reverse, hidden=pane.show_hidden,
                system=pane.show_system, extensions=pane.show_extensions, mode=pane.view_mode))
        groups.append(dict(tabs=panes, selected=tabs.index(tabs.select())))
    if sum(len(g['tabs']) for g in groups) > 80:
        raise ValueError(tr('A workspace can contain at most 80 tabs.'))
    return dict(groups=groups, panels=app.panel_count_var.get(), multi=app._multi_panel_count,
                ratio=app._tree_ratio, active=app.panel_tabs.index(app._tabs_for(app.active)),
                order=[(app.panel_tabs.index(app._tabs_for(p)), app._tabs_for(p).index(p))
                       for p in app.single_tabs._tabs if p in app.all_panes()])


def validate_workspace(data):
    if not isinstance(data, dict): raise ValueError('Invalid workspace.')
    groups = data.get('groups')
    if not isinstance(groups, list) or len(groups) != 4: raise ValueError('Invalid workspace groups.')
    total = 0
    missing = []
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get('tabs'), list) or not group['tabs']:
            raise ValueError('Invalid workspace tabs.')
        total += len(group['tabs'])
        for pane in group['tabs']:
            if not isinstance(pane, dict) or not isinstance(pane.get('path'), str):
                raise ValueError('Invalid workspace path.')
            if not Path(pane['path']).is_dir(): missing.append(pane['path'])
            if pane.get('lock') not in ('unlocked', 'locked', 'reset'):
                raise ValueError('Invalid tab lock.')
            if not isinstance(pane.get('locked_path', pane['path']), str):
                raise ValueError('Invalid locked path.')
            if not isinstance(pane.get('color', 'default'), str):
                raise ValueError('Invalid tab color.')
    if total > 80: raise ValueError('A workspace can contain at most 80 tabs.')
    if data.get('panels') not in range(1, 5) or data.get('multi') not in range(2, 5):
        raise ValueError('Invalid panel count.')
    if not isinstance(data.get('ratio'), (int, float)) or not .15 <= data['ratio'] <= .65:
        raise ValueError('Invalid tree ratio.')
    if not isinstance(data.get('order', []), list):
        raise ValueError('Invalid shared tab order.')
    if missing:
        raise OSError(tr('Saved path is unavailable')+':\n'+'\n'.join(missing[:12])+
                      '\n'+tr('No tabs were changed. Restore the paths or update this saved workspace.'))
    return groups


def restore_workspace(app, data):
    groups = validate_workspace(data)  # Validate every path before touching tabs.
    backup = capture_workspace(app)
    if not messagebox.askyesno(tr('Workspaces'),
            tr('Replace the current tabs and layout? Your current workspace is saved as Before switching. '
               'Files and global preferences are not changed.'), parent=app):
        return False
    records = WorkflowRecords(app.config_data, 'workspace_undo')
    records.put('Before switching', backup)
    app.save_config()
    previous_ready, previous_busy, previous_single = app._ready, app._single_busy, app._single_layout
    app._ready = False; app._single_busy = True; app._single_layout = False
    old = [list(tabs.panes()) for tabs in app.panel_tabs]
    created = []
    try:
        for tabs, group in zip(app.panel_tabs, groups):
            items = []
            for item in group['tabs']:
                pane = tabs.add_tab(Path(item['path']), notify=False, position=len(tabs.tabs()))
                value=item.get('tab_group','')
                pane.tab_group=value.strip()[:40] if isinstance(value,str) and not any(ord(c)<32 for c in value) else ''
                created.append((tabs, pane)); items.append(pane)
                pane.sort_column = item.get('sort', 'name') if item.get('sort') in pane.all_sort_columns else 'name'
                pane.reverse = bool(item.get('descending'))
                pane.show_hidden = bool(item.get('hidden')); pane.show_system = bool(item.get('system'))
                pane.show_extensions = bool(item.get('extensions', True))
                pane.view_mode = item.get('mode', 'list') if item.get('mode') in {'list', 'folder', 'file'} else 'list'
                pane.set_quick_filter(str(item.get('filter', '')))
                pane.lock_mode = item['lock']
                locked = Path(item.get('locked_path', item['path']))
                pane.locked_path = (locked if locked.is_dir() else pane.path) if pane.lock_mode != 'unlocked' else None
                tabs.set_color(pane, item.get('color', 'default'), notify=False)
                tabs.set_lock(pane, pane.lock_mode, notify=False)
                pane.set_active_appearance(False, app.palette)
                pane._update_view_mode_button(); pane.refresh()
            selected = group.get('selected', 0)
            selected = selected if isinstance(selected, int) else 0
            tabs.select(items[max(0, min(len(items)-1, selected))])
        for tabs, panes in zip(app.panel_tabs, old):
            for pane in panes:
                tabs.forget(pane); tabs.on_close_archive(pane); pane.destroy()
        app.panel_count_var.set(data['panels']); app._multi_panel_count = data['multi']; app._tree_ratio = data['ratio']
        active = data.get('active', 0)
        app.active = app.panel_tabs[active if isinstance(active, int) and 0 <= active < 4 else 0].current()
        order = []
        for pair in data.get('order', []):
            if isinstance(pair, (list, tuple)) and len(pair) == 2:
                group, index = pair
                if isinstance(group, int) and isinstance(index, int) and 0 <= group < 4:
                    panes = app.panel_tabs[group].panes()
                    if 0 <= index < len(panes) and panes[index] not in order: order.append(panes[index])
        app.single_tabs._tabs = order
    except Exception:
        for tabs, pane in created:
            if pane.winfo_exists(): tabs.forget(pane); pane.destroy()
        for tabs, panes in zip(app.panel_tabs, old):
            if panes and panes[0].winfo_exists(): tabs.select(panes[0])
        app.active = app.panel_tabs[0].current()
        raise
    finally:
        app._ready, app._single_busy, app._single_layout = previous_ready, previous_busy, previous_single
    app.apply_panel_count(); app.apply_column_settings(); app.apply_color_scheme(save=False)
    app.active.focus_file_list()
    app.save_config()
    return True


def show_workspaces(app):
    picker = WorkflowPicker(app, 'Workspaces', WorkflowRecords(app.config_data, 'workspaces'),
        app.save_config, lambda: capture_workspace(app), lambda d: restore_workspace(app, d),
        lambda d: tr('{count} tab(s)', count=sum(len(g.get('tabs', [])) for g in d.get('groups', []) if isinstance(g, dict))))
    return picker
