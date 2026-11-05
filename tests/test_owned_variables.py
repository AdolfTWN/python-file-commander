import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from pycommander.app import Commander
from pycommander.dialogs import release_owned_variables


class OwnedVariableTests(unittest.TestCase):
    def variable(self):
        variable=Mock(spec=tk.Variable)
        variable.trace_info.return_value=[(('write',),'owned_callback')]
        return variable

    def test_explicit_owned_groups_release_traces_without_sweeping_shared_preferences(self):
        first,second,shared=self.variable(),self.variable(),self.variable()
        owner=SimpleNamespace(draft={'a':first},prefix_rows=[(object(),second,object())],shared=shared)
        release_owned_variables(owner,'draft','prefix_rows')
        first.trace_remove.assert_called_once_with(('write',),'owned_callback')
        second.trace_remove.assert_called_once_with(('write',),'owned_callback')
        shared.trace_remove.assert_not_called()
        self.assertIsNone(owner.draft);self.assertIsNone(owner.prefix_rows)
        self.assertIs(owner.shared,shared)
        release_owned_variables(owner,'draft','prefix_rows')

    def test_geometry_saves_ignore_descendant_configures_but_keep_root_and_explicit_requests(self):
        owner=SimpleNamespace(_ready=True,_save_job=None,after=Mock(return_value='job'),
                              after_cancel=Mock(),save_config=Mock())
        Commander._schedule_save(owner,SimpleNamespace(widget=object()))
        owner.after.assert_not_called()
        Commander._schedule_save(owner,SimpleNamespace(widget=owner))
        owner.after.assert_called_once_with(250,owner.save_config)
        Commander._schedule_save(owner)
        owner.after_cancel.assert_called_once_with('job')
        self.assertEqual(owner.after.call_count,2)
