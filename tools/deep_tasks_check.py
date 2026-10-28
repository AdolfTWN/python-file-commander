"""Behavioral exploratory regressions: filesystem state, safety, nested dialogs."""
import importlib
import gc
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
import weakref
from tkinter import simpledialog
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
pfc=importlib.import_module('pfc' if 'pfc' in sys.argv else 'pycommander.app')
sys.argv=[arg for arg in sys.argv if arg!='pfc']


def pump(root,seconds=.1):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        root.update();time.sleep(.005)


class DeepTasks(unittest.TestCase):
    def setUp(self):
        # Repeated independent interpreters are a harness stress case. Finalize
        # retired Tk variables on their owning thread, not the next I/O worker.
        gc.collect()
        self.temp=tempfile.TemporaryDirectory(prefix='pfc-deep-')
        self.root=Path(self.temp.name)
        ini=self.root/'pfc.ini'
        pfc.Commander._find_ini_path=staticmethod(lambda:ini)
        pfc.Commander._sync_auto_start=lambda *a,**kw:True
        pfc.Commander._start_windows_tray=lambda *a:None
        self.app=pfc.Commander();self.app.auto_font_size_var.set(False)
        self.errors=[];self.app.report_callback_exception=lambda *exc:self.errors.append(str(exc))
        self.folder=self.root/'Project';self.folder.mkdir()
        (self.folder/'alpha.md').write_text('# Alpha\n',encoding='utf-8')
        (self.folder/'beta.txt').write_text('beta\n',encoding='utf-8')
        self.pane=self.app.active;self.pane.navigate(self.folder);pump(self.app)

    def tearDown(self):
        log=self.app.debug_log;self.app.close_app();self.temp.cleanup()
        self.assertIsNone(log.error_handler);self.assertFalse(log._hooks)
        self.assertFalse(self.errors,self.errors)
        self.pane=None;self.app=None;gc.collect()

    def test_unavailable_child_does_not_break_numeric_sort(self):
        link=self.folder/'missing-link'
        try:link.symlink_to(self.folder/'missing')
        except OSError:self.skipTest('Symlink fixture unavailable')
        for column in ('size','modified','ext','name'):
            self.pane.sort_column=column
            self.pane.refresh()
            self.assertIn(self.folder/'alpha.md',self._paths())

    def _paths(self):
        return [Path(self.pane.tree.item(i,'tags')[0]) for i in self.pane.tree.get_children()]

    def test_failed_navigation_keeps_path_history_and_list(self):
        bad=self.root/'Unavailable';bad.mkdir()
        old=(self.pane.path,list(self.pane.history),self._paths())
        original=Path.iterdir
        def listing(path):
            if path==bad:raise PermissionError('isolated unavailable folder')
            return original(path)
        with patch.object(Path,'iterdir',listing),patch.object(pfc.messagebox,'showerror'):
            self.assertFalse(self.pane.navigate(bad))
        self.assertEqual(old,(self.pane.path,self.pane.history,self._paths()))

    def test_failed_refresh_does_not_erase_visible_rows(self):
        old=self._paths();original=Path.iterdir
        def listing(path):
            if path==self.folder:raise PermissionError('isolated unavailable folder')
            return original(path)
        with patch.object(Path,'iterdir',listing),patch.object(pfc.messagebox,'showerror'):
            self.pane.refresh()
        self.assertEqual(old,self._paths())

    def test_watcher_read_failure_warns_once_and_recovers_without_content_change(self):
        old=self._paths();original=Path.iterdir
        def denied(path):
            if path==self.folder:raise PermissionError(13,'isolated denial')
            return original(path)
        with patch.object(Path,'iterdir',denied),patch.object(self.app.debug_log,'exception') as logged:
            for _ in range(3):self.assertFalse(self.pane.refresh_if_changed())
            self.pane.set_quick_filter('alpha');self.pane.change_sort('size')
            self.pane.apply_scale(1.5)
            self.assertFalse(self.pane.refresh_if_changed())
            self.assertEqual(1,logged.call_count)
            self.assertIn(pfc.tr('Cannot read folder; previous list retained'),self.pane.status.cget('text'))
        self.pane.clear_quick_filter()
        self.assertTrue(self.pane.refresh_if_changed())
        # The outage workflow explicitly switched to size sorting. Recovery
        # must preserve that preference, not restore the original name order.
        self.assertEqual(sorted(old,key=lambda path:path.stat().st_size),self._paths())
        self.assertIsNone(self.pane._listing_failure_key)
        self.assertNotIn(pfc.tr('Cannot read folder; previous list retained'),self.pane.status.cget('text'))

    def test_vcs_worker_does_not_capture_tk_ownership(self):
        self.app.vcs_overlay_var.set(True)
        self.pane._vcs_inflight=None;self.pane._vcs_path=None
        with patch.object(pfc.threading,'Thread') as thread:
            self.pane._request_vcs_statuses()
            target=thread.call_args.kwargs['target']
            self.assertNotIn('self',target.__code__.co_freevars)
            self.assertFalse(any(isinstance(cell.cell_contents,pfc.tk.Misc) for cell in target.__closure__))

    def test_quick_filter_reuses_current_snapshot(self):
        original=Path.stat;calls=[]
        def stat(path,*args,**kw):
            if path.parent==self.folder:calls.append(path)
            return original(path,*args,**kw)
        with patch.object(Path,'stat',stat):self.pane.set_quick_filter('alpha')
        self.assertEqual([self.folder/'alpha.md'],self._paths())
        self.assertEqual([],calls,'Quick filter reread filesystem metadata')
        self.pane.clear_quick_filter();self.assertEqual(2,len(self._paths()))

    def test_folder_and_transfer_workers_do_not_own_tk_widgets(self):
        nav=self.app.folder_tree
        module=pfc if pfc.__name__=='pfc' else importlib.import_module('pycommander.singlepanel')
        worker_folder=self.folder/'Worker';worker_folder.mkdir()
        iid=nav._node(worker_folder,nav.pc)
        def independent(target,seen=None):
            seen=set() if seen is None else seen
            if id(target) in seen:return
            seen.add(id(target))
            for cell in target.__closure__ or ():
                value=cell.cell_contents
                self.assertNotIsInstance(value,pfc.tk.Misc,'Worker retains Tk ownership')
                if callable(value) and hasattr(value,'__closure__'):independent(value,seen)
        with patch.object(module.threading,'Thread') as thread:
            nav.load(iid);independent(thread.call_args.kwargs['target'])
            nav.pending.pop(iid);nav.slots.release()
            nav._probe_cancel=None;nav._visible_nodes=[iid]
            with patch.object(nav.tree,'winfo_viewable',return_value=True):nav._probe_visible()
            independent(thread.call_args.kwargs['target'])
            nav._probe_cancel=None
        for kind in (pfc.TransferProgress,pfc.SyncProgress):
            with patch.object(pfc.threading,'Thread') as thread:
                if kind is pfc.TransferProgress:
                    window=kind(self.app,'Copy',lambda *a:pfc.OperationResult(),[],self.root,lambda *a:'skip',True)
                else:window=kind(self.app,[],lambda *a:'skip',True)
                independent(thread.call_args.kwargs['target'])
                variable=weakref.ref(window.target_var) if kind is pfc.TransferProgress else None
                window.grab_release();window.destroy()
                if variable is not None:self.assertIsNone(variable(),'Destroy must release the owned Tk variable on the UI thread')

    def test_reading_scale_reuses_metadata_but_normal_refresh_observes_new_files(self):
        original=Path.stat;calls=[]
        def stat(path,*args,**kw):
            if path.parent==self.folder:calls.append(path)
            return original(path,*args,**kw)
        with patch.object(Path,'stat',stat):self.pane.apply_scale(1.5)
        self.assertEqual([],calls,'Presentation-only scale reread file metadata')
        new=self.folder/'new.txt';new.write_text('new')
        self.pane.refresh_if_changed();self.assertIn(new,self._paths())

    def test_folder_tree_sort_read_failure_does_not_clear_previous_nodes(self):
        (self.folder/'Module').mkdir()
        self.pane.view_mode='folder';self.pane.refresh();old=self.pane.tree.get_children()
        original=Path.iterdir
        def denied(path):
            if path==self.folder:raise PermissionError(13,'isolated denial')
            return original(path)
        with patch.object(Path,'iterdir',denied),patch.object(pfc.messagebox,'showerror'):
            self.pane.change_sort('name')
        self.assertEqual(old,self.pane.tree.get_children())

    def test_result_tab_keeps_explicit_scope_after_sort_filter_refresh(self):
        other=self.root/'Elsewhere';other.mkdir();external=other/'external.md';external.write_text('external')
        expected={self.folder/'alpha.md',external}
        self.pane.show_file_listing(list(expected),'Isolated results')
        for column in ('name','size','modified','ext'):
            self.pane.change_sort(column);self.assertEqual(expected,set(self._paths()))
        self.pane.set_quick_filter('external');self.assertEqual([external],self._paths())
        self.pane.clear_quick_filter();self.pane.refresh();self.assertEqual(expected,set(self._paths()))
        external.unlink();self.pane.refresh();self.assertEqual([self.folder/'alpha.md'],self._paths())
        # Real recursive searches commonly return duplicate basenames. One
        # disappearing source must not break the remaining actionable results.
        duplicate=other/'alpha.md';duplicate.write_text('another result')
        self.pane.show_file_listing([self.folder/'alpha.md',duplicate],'Duplicates')
        duplicate.unlink();self.pane.refresh()
        self.assertEqual([self.folder/'alpha.md'],self._paths())

    def test_refresh_updates_cached_filter_snapshot(self):
        self.pane.set_quick_filter('gamma')
        added=self.folder/'gamma.txt';added.write_text('added')
        self.pane.refresh_if_changed();self.assertEqual([added],self._paths())
        added.unlink();self.pane.refresh_if_changed();self.assertEqual([],self._paths())
        self.pane.clear_quick_filter();self.assertEqual(2,len(self._paths()))

    def test_closed_pane_does_not_leave_its_poll_or_resize_timers(self):
        pane=self.app.left_tabs.add_tab(self.folder);pump(self.app)
        commands=set(pane._tclCommands or ())
        self.app.left_tabs.forget(pane);pane.destroy()
        for job in self.app.tk.call('after','info'):
            script=self.app.tk.call('after','info',job)[0]
            self.assertFalse(any(command in script for command in commands),script)
        pump(self.app,.2)

    def test_scaled_typed_inputs_validate_and_restore_nested_modal(self):
        module=pfc if pfc.__name__=='pfc' else importlib.import_module('pycommander.dialogs')
        outer=pfc.tk.Toplevel(self.app);outer.grab_set()
        entry=pfc.ttk.Entry(outer);entry.pack();entry.focus_force();pump(self.app)
        dialog=module.ScaledInputDialog(outer,'Number','Bounded value','integer',dict(minvalue=1,maxvalue=9))
        dialog.entry.insert(0,'bad');dialog.accept();pump(self.app)
        self.assertTrue(dialog.winfo_exists());self.assertTrue(dialog.error.winfo_ismapped())
        dialog.entry.delete(0,'end');dialog.entry.insert(0,'10');dialog.accept()
        self.assertTrue(dialog.winfo_exists())
        dialog.entry.delete(0,'end');dialog.entry.insert(0,'4');dialog.accept()
        self.assertEqual(4,dialog.result);self.assertIs(self.app.grab_current(),outer)
        dialog=module.ScaledInputDialog(outer,'Cancel','Do not accept','string',dict(initialvalue='draft'))
        dialog.cancel_button.focus_force();pump(self.app);dialog.cancel_button.event_generate('<Return>');pump(self.app)
        self.assertIsNone(dialog.result);self.assertIs(self.app.grab_current(),outer)
        for value in ('NaN','Inf','-Inf'):
            dialog=module.ScaledInputDialog(outer,'Float','Finite','float')
            dialog.entry.insert(0,value);dialog.accept();self.assertTrue(dialog.winfo_exists());dialog.cancel()
        outer.destroy()

    def test_public_typed_prompt_returns_exact_type_and_keeps_cancel(self):
        module=pfc if pfc.__name__=='pfc' else importlib.import_module('pycommander.dialogs')
        for ask,value,expected in ((simpledialog.askstring,'review','review'),
                                   (simpledialog.askinteger,'12',12),(simpledialog.askfloat,'1.25',1.25)):
            def accept():
                dialog=next(w for w in self.app.winfo_children() if isinstance(w,module.ScaledInputDialog))
                dialog.entry.insert(0,value);dialog.accept()
            self.app.after(20,accept)
            result=ask('Typed prompt','Isolated input',parent=self.app)
            self.assertEqual(expected,result);self.assertIs(type(expected),type(result))
        def cancel():
            next(w for w in self.app.winfo_children() if isinstance(w,module.ScaledInputDialog)).cancel()
        self.app.after(20,cancel)
        self.assertIsNone(simpledialog.askstring('Cancel','No write',parent=self.app))

    def test_message_details_remain_keyboard_scrollable(self):
        module=pfc if pfc.__name__=='pfc' else importlib.import_module('pycommander.dialogs')
        dialog=module.ScaledMessageDialog(self.app,dict(type='okcancel',message='\n'.join('Detail '+str(i) for i in range(100))))
        dialog.text.focus_force();pump(self.app)
        before=dialog.text.yview()[0]
        dialog.text.event_generate('<Next>');pump(self.app)
        self.assertGreater(dialog.text.yview()[0],before)
        dialog.choose('cancel')

    @unittest.skipUnless(hasattr(os,'mkfifo'),'POSIX special stream fixture')
    def test_plain_preview_refuses_special_stream_without_blocking_tk(self):
        fifo=self.folder/'stream.txt';os.mkfifo(fifo)
        started=time.monotonic();self.app.preview_paths([fifo],fifo);pump(self.app)
        self.assertLess(time.monotonic()-started,2)
        page=self.app.preview_window.active_page
        self.assertIn(pfc.tr('Cannot preview file'),page.status.cget('text'))
        self.assertIn('ordinary file',page.text.get('1.0','end'))
        self.app.preview_window.close();self.app.preview_window=None

    def test_workflow_filter_opens_the_matching_record_and_restores_grab(self):
        module=pfc if pfc.__name__=='pfc' else importlib.import_module('pycommander.workflows')
        data=pfc if pfc.__name__=='pfc' else importlib.import_module('pycommander.workflowdata')
        records=data.WorkflowRecords(self.app.config_data,'audit')
        for i in range(40):records.put('Project '+str(i),dict(path='location '+str(i)))
        outer=pfc.tk.Toplevel(self.app);outer.grab_set();opened=[]
        dialog=module.WorkflowPicker(outer,'Workspaces',records,lambda:None,lambda:None,
                                    lambda value:opened.append(value),lambda value:value['path'])
        dialog.query.set('location 23');pump(self.app)
        self.assertEqual(['Project 23'],[item['name'] for item in dialog.entries])
        with patch.object(pfc.messagebox,'showinfo') as detail:
            dialog.show_details();self.assertEqual('Project 23\n\nlocation 23',detail.call_args.args[1])
        dialog.open();self.assertEqual([dict(path='location 23')],opened)
        self.assertIs(self.app.grab_current(),outer);outer.destroy()

    def test_transfer_io_is_off_tk_conflicts_on_tk_and_result_returned(self):
        destination=self.root/'Destination';destination.mkdir()
        source=self.folder/'alpha.md';(destination/source.name).write_text('old')
        worker_threads=[];resolver_threads=[];ticks=[]
        def copy(items,target,resolver,continue_errors):
            worker_threads.append(threading.current_thread());time.sleep(.12)
            return pfc.copy_items(items,target,resolver,continue_errors)
        def resolver(source,target):resolver_threads.append(threading.current_thread());return 'replace'
        self.app.after(30,lambda:ticks.append(1))
        with patch.object(self.app,'_conflict_resolver',return_value=resolver):
            result=self.app._execute_transfer('Copy',copy,[source],destination,confirm=False)
        self.assertEqual([source],result.completed);self.assertTrue(ticks)
        self.assertTrue(all(t is not threading.main_thread() for t in worker_threads))
        self.assertEqual([threading.main_thread()],resolver_threads)
        self.assertEqual(source.read_bytes(),(destination/source.name).read_bytes())

    def test_transfer_cancel_finishes_current_item_and_marks_remaining_skipped(self):
        destination=self.root/'Destination';items=[self.folder/'alpha.md',self.folder/'beta.txt']
        def slow(*args):time.sleep(.15);return pfc.copy_items(*args)
        self.app.after(60,lambda:self.app._transfer_dialog.cancel())
        with patch.object(self.app,'_show_operation_result'):
            result=self.app._execute_transfer('Copy',slow,items,destination,confirm=False)
        self.assertEqual(items[:1],result.completed);self.assertEqual(items[1:],result.skipped)
        self.assertFalse((destination/items[1].name).exists())

    def test_transfer_conflict_choices_and_stop_on_failure(self):
        source=self.folder/'alpha.md'
        for action in ('skip','keep_both','cancel'):
            destination=self.root/action;destination.mkdir();(destination/source.name).write_text('old')
            with patch.object(self.app,'_conflict_resolver',return_value=lambda *a:action),patch.object(self.app,'_show_operation_result'):
                result=self.app._execute_transfer('Copy',pfc.copy_items,[source],destination,confirm=False)
            self.assertEqual('old',(destination/source.name).read_text())
            self.assertEqual([source],result.completed if action=='keep_both' else result.skipped)
        missing=self.folder/'missing.txt';self.app.continue_errors_var.set(False)
        with patch.object(self.app,'_show_operation_result'):
            result=self.app._execute_transfer('Move',pfc.move_items,[missing,source],self.root/'Failed',confirm=False)
        self.assertEqual([missing],[failure.source for failure in result.failures])
        self.assertEqual([source],result.skipped);self.assertTrue(source.exists())

    def test_transfer_moves_a_folder_without_losing_nested_bytes(self):
        folder=self.folder/'Nested';(folder/'Deep').mkdir(parents=True)
        data=bytes(range(256))*100;(folder/'Deep'/'data.bin').write_bytes(data)
        destination=self.root/'Moved'
        result=self.app._execute_transfer('Move',pfc.move_items,[folder],destination,confirm=False)
        self.assertEqual([folder],result.completed);self.assertFalse(folder.exists())
        self.assertEqual(data,(destination/folder.name/'Deep'/'data.bin').read_bytes())

    def test_command_shortcuts_scale_without_clipping_or_losing_selection(self):
        self.app.font_size_var.set('300');self.app.apply_font_size(save=False)
        self.app.show_command_palette();dialog=self.app.grab_current();pump(self.app)
        for width in (760,1200,760):
            dialog.geometry(f'{width}x750');pump(self.app)
            font=pfc.tkfont.nametofont('TkDefaultFont')
            maximum=max(font.measure(str(item[2])) for item in dialog.commands)+12
            self.assertGreaterEqual(dialog.list.column('key','width'),maximum)
            self.assertTrue(dialog.list.selection())
        dialog.close()

    def test_resolver_fault_is_failure_not_user_cancel_in_copy_and_safe_sync(self):
        source=self.folder/'alpha.md';destination=self.root/'Fault';destination.mkdir()
        (destination/source.name).write_text('protected')
        def failed(*_args):raise RuntimeError('isolated resolver failure')
        with patch.object(self.app,'_conflict_resolver',return_value=failed),patch.object(self.app,'_show_operation_result'):
            result=self.app._execute_transfer('Copy',pfc.copy_items,[source,self.folder/'beta.txt'],destination,confirm=False)
            self.assertEqual([source],[f.source for f in result.failures])
            self.assertEqual([self.folder/'beta.txt'],result.skipped)
            result=self.app.execute_sync_plans([(source,destination/source.name)])
            self.assertEqual([source],[f.source for f in result.failures]);self.assertFalse(result.skipped)
        self.assertEqual('protected',(destination/source.name).read_text())

    def test_handled_failures_log_safe_counts_but_cancel_does_not(self):
        log=self.app.debug_log
        result=pfc.OperationResult(failures=[pfc.OperationFailure(self.folder/'alpha.md',None,'private raw detail')])
        with patch.object(log,'event') as event:
            dialog=self.app._show_operation_result('Copy',result);dialog.destroy()
            self.assertEqual('operation.partial.failed',event.call_args.args[0])
            metadata=event.call_args.kwargs
            self.assertEqual('ERROR',metadata['severity']);self.assertEqual(1,metadata['failed'])
            self.assertNotIn(str(self.folder),str(metadata));self.assertNotIn('private',str(metadata))
            event.reset_mock()
            dialog=self.app._show_operation_result('Copy',pfc.OperationResult(skipped=[self.folder/'alpha.md']));dialog.destroy()
            event.assert_not_called()

    def test_invalid_worker_result_does_not_strand_the_progress_dialog(self):
        self.app.continue_errors_var.set(False)
        items=[self.folder/'alpha.md',self.folder/'beta.txt']
        with patch.object(self.app,'_show_operation_result'):
            result=self.app._execute_transfer('Copy',lambda *args:None,items,self.root/'Unused',confirm=False)
        self.assertEqual([items[0]],[f.source for f in result.failures]);self.assertEqual(items[1:],result.skipped)
        self.assertIsNone(self.app._transfer_dialog)

    def test_result_details_are_complete_and_retry_only_failed(self):
        failed=self.folder/'alpha.md';skipped=self.folder/'beta.txt'
        message='A full recoverable failure '+('detail '*100)
        result=pfc.OperationResult(skipped=[skipped],failures=[pfc.OperationFailure(failed,None,message)])
        retries=[];dialog=self.app._show_operation_result('Copy',result,retry=lambda paths:retries.append(paths))
        pump(self.app)
        self.assertIn(message,dialog.detail.get('1.0','end'));dialog.copy_button.invoke()
        self.assertIn(str(skipped),self.app.clipboard_get())
        dialog.retry_button.invoke();self.assertEqual([[failed]],retries)

    def test_progress_burst_is_coalesced_and_root_cannot_abandon_active_write(self):
        ticks=[];results=[];gate=threading.Event()
        def work(report):
            for i in range(100000):report(i,100000,'Isolated burst '+str(i))
            gate.wait(3);return 'finished'
        self.app._run_progress_operation('Copy',work,results.append)
        self.app.after(30,lambda:ticks.append(1))
        pump(self.app,.2);self.assertTrue(ticks)
        self.app.close_app();self.assertTrue(self.app.winfo_exists())
        gate.set();deadline=time.monotonic()+4
        while not results and time.monotonic()<deadline:pump(self.app,.02)
        self.assertEqual(['finished'],results);self.assertFalse(self.app._progress_operations)

    def test_message_enter_activates_focused_cancel(self):
        module=pfc if pfc.__name__=='pfc' else importlib.import_module('pycommander.dialogs')
        dialog=module.ScaledMessageDialog(self.app,dict(type='okcancel',message='Isolated test',title='Task'))
        dialog.buttons['cancel'].focus_force();pump(self.app)
        dialog.buttons['cancel'].event_generate('<Return>');pump(self.app)
        self.assertEqual('cancel',dialog.result)

    def test_conflict_cancel_is_safe_default_and_restores_modal(self):
        outer=pfc.tk.Toplevel(self.app);outer.grab_set()
        entry=pfc.ttk.Entry(outer);entry.pack();entry.focus_force();pump(self.app)
        dialog=pfc.ConflictDialog(outer,self.folder/'alpha.md',self.folder/'beta.txt');pump(self.app)
        focused=self.app.focus_get()
        self.assertIsNotNone(focused)
        text=focused.cget('text')
        dialog.choose('cancel');pump(self.app)
        restored=self.app.grab_current()
        outer.destroy()
        self.assertEqual(pfc.tr('Cancel'),text,'Conflict initially focuses destructive Replace')
        self.assertIs(restored,outer)

    def test_rename_invalid_counters_disable_apply(self):
        win=pfc.MultiRenameWindow(self.app,[self.folder/'alpha.md'],[],lambda:None)
        try:
            win.mask_var.set('[N]_[C]')
            for start,digits in [('bad','2'),('-1','2'),('1','0'),('1','13')]:
                win.start_var.set(start);win.digits_var.set(digits);pump(self.app)
                self.assertTrue(win.apply_button.instate(['disabled']),(start,digits))
        finally:win.destroy()

    def test_rename_typing_coalesces_preview_work(self):
        win=pfc.MultiRenameWindow(self.app,[self.folder/'alpha.md'],[],lambda:None)
        pump(self.app);calls=[];original=win.update_preview
        def update():calls.append(1);return original()
        win.update_preview=update
        for i in range(25):win.find_var.set(str(i))
        pump(self.app);win.destroy()
        self.assertLessEqual(len(calls),1,'Every trace enqueued a full preview')


if __name__=='__main__':unittest.main()
