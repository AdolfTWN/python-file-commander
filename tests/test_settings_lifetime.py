from types import SimpleNamespace
import unittest

from pycommander.settings import SettingsDialog


class SettingsLifetimeTests(unittest.TestCase):
    def test_destroying_dialog_does_not_reenter_layout_or_nested_idle_processing(self):
        # These entry points can receive synchronous focus/configure callbacks
        # while Tk recursively destroys child widgets. No widget access or
        # nested update_idletasks is allowed once teardown starts.
        owner=SimpleNamespace(_destroying=True)
        for name,args in (('_layout_navigation',(None,)),('_resize',(None,)),
                          ('_scroll_region',()),('_layout_cards',(500,)),
                          ('show_page',('appearance',)),('_show_page_top',()),
                          ('_schedule_shots',()),('_update_shots',()),('_reveal_focus',(None,))):
            with self.subTest(callback=name):getattr(SettingsDialog,name)(owner,*args)


if __name__=='__main__':unittest.main()
