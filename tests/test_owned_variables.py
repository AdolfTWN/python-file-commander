import tkinter as tk
from tkinter import font as tkfont
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pycommander.app import Commander
from pycommander.dialogs import release_owned_variables, release_owned_images, release_owned_fonts


class OwnedVariableTests(unittest.TestCase):
    def test_owned_fonts_are_deleted_once_without_deleting_borrowed_named_fonts(self):
        font=tkfont.Font.__new__(tkfont.Font);font.delete_font=True
        shared=tkfont.Font.__new__(tkfont.Font);shared.delete_font=False
        owner=SimpleNamespace(owned=font,styles={'same':font,'borrowed':shared})
        with patch.object(tkfont.Font,'__del__',autospec=True) as dispose:
            release_owned_fonts(owner,'owned','styles')
            dispose.assert_called_once_with(font)
        self.assertFalse(font.delete_font);self.assertFalse(shared.delete_font)
        self.assertIsNone(owner.owned);self.assertIsNone(owner.styles)

    def test_owned_images_are_disposed_on_close_and_duplicate_references_are_safe(self):
        image=tk.Image.__new__(tk.Image);image.name='pyimage1'
        shared=Mock(spec=tk.Image);shared.name='shared'
        owner=SimpleNamespace(images=[image],original=image,shared=shared)
        with patch.object(tk.Image,'__del__',autospec=True) as dispose:
            release_owned_images(owner,'images','original')
            dispose.assert_called_once_with(image)
        self.assertIsNone(image.name)
        self.assertIsNone(owner.images);self.assertIsNone(owner.original)
        self.assertEqual(shared.name,'shared')
        release_owned_images(owner,'images','original')

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
