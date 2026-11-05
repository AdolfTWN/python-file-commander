import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from pycommander.flowlayout import schedule_owned_idle, schedule_owned_after


class OwnedIdleTests(unittest.TestCase):
    def widget(self):
        return SimpleNamespace(winfo_exists=Mock(return_value=True),
                               after_idle=Mock(return_value='token'),after=Mock(return_value='timed'),after_cancel=Mock(),bind=Mock())

    def test_timer_and_idle_share_ownership_but_different_keys(self):
        widget=self.widget();callback=Mock()
        self.assertEqual(schedule_owned_after(widget,'poll',60,callback),'timed')
        schedule_owned_after(widget,'poll',60,callback)
        widget.after.assert_called_once()
        widget.after.call_args.args[1]()
        callback.assert_called_once_with()
        schedule_owned_idle(widget,'layout',Mock())
        self.assertEqual(widget.bind.call_count,1)

    def test_duplicate_layout_is_coalesced_and_callback_can_schedule_again(self):
        widget=self.widget();callback=Mock()
        self.assertEqual(schedule_owned_idle(widget,'layout',callback),'token')
        schedule_owned_idle(widget,'layout',callback)
        widget.after_idle.assert_called_once()
        widget.after_idle.call_args.args[0]()
        callback.assert_called_once()
        self.assertFalse(widget._pfc_owned_idle_jobs)
        schedule_owned_idle(widget,'layout',callback)
        self.assertEqual(widget.after_idle.call_count,2)

    def test_only_owner_destroy_cancels_its_jobs(self):
        widget=self.widget();schedule_owned_idle(widget,'layout',Mock())
        destroyed=widget.bind.call_args.args[1]
        destroyed(SimpleNamespace(widget=object()));widget.after_cancel.assert_not_called()
        destroyed(SimpleNamespace(widget=widget));widget.after_cancel.assert_called_once_with('token')
        self.assertFalse(widget._pfc_owned_idle_jobs)

    def test_destroyed_widgets_do_not_schedule(self):
        widget=self.widget();widget.winfo_exists.return_value=False
        self.assertIsNone(schedule_owned_idle(widget,'layout',Mock()))
        widget.after_idle.assert_not_called()
