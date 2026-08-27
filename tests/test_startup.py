import struct
import unittest
from pathlib import Path

from pycommander.icons import pfc_icon_ico
from pycommander.startup import (AUTOSTART_KEY, AUTOSTART_VALUE,
                                 set_windows_autostart, startup_command)


class _Key:
    def __init__(self, registry):
        self.registry = registry

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Registry:
    HKEY_CURRENT_USER = object()
    REG_SZ = 1
    KEY_SET_VALUE = 2

    def __init__(self):
        self.values = {}

    def CreateKey(self, root, path):
        self.last_open = (root, path)
        return _Key(self)

    def OpenKey(self, root, path, reserved, access):
        self.last_open = (root, path, reserved, access)
        if AUTOSTART_VALUE not in self.values:
            raise FileNotFoundError
        return _Key(self)

    def SetValueEx(self, _key, name, reserved, kind, value):
        self.values[name] = (reserved, kind, value)

    def DeleteValue(self, _key, name):
        del self.values[name]


class StartupTests(unittest.TestCase):
    def test_portable_script_prefers_pythonw_and_quotes_paths(self):
        command = startup_command(
            Path(r"C:\Program Files\Python\python.exe"),
            Path(r"C:\My Apps\PFC\pfc.py"), frozen=False,
            pythonw_exists=lambda _path: True)
        self.assertEqual(
            command,
            '"C:\\Program Files\\Python\\pythonw.exe" '
            '"C:\\My Apps\\PFC\\pfc.py" --startup')

    def test_frozen_edition_registers_only_the_executable(self):
        command = startup_command(Path(r"C:\PFC\pfc.exe"), frozen=True)
        self.assertEqual(command, r"C:\PFC\pfc.exe --startup")

    def test_registry_value_can_be_enabled_then_cancelled(self):
        registry = _Registry()
        self.assertTrue(set_windows_autostart(True, "pfc command", registry))
        self.assertEqual(registry.last_open[:2],
                         (registry.HKEY_CURRENT_USER, AUTOSTART_KEY))
        self.assertEqual(registry.values[AUTOSTART_VALUE][2], "pfc command")
        self.assertTrue(set_windows_autostart(False, registry=registry))
        self.assertNotIn(AUTOSTART_VALUE, registry.values)

    def test_cancel_is_idempotent_when_no_registry_value_exists(self):
        registry = _Registry()
        self.assertTrue(set_windows_autostart(False, registry=registry))

    def test_tray_icon_is_a_single_png_backed_ico(self):
        icon = pfc_icon_ico(32)
        self.assertEqual(struct.unpack("<HHH", icon[:6]), (0, 1, 1))
        width, height, _colors, _reserved, planes, depth, size, offset = struct.unpack(
            "<BBBBHHII", icon[6:22])
        self.assertEqual((width, height, planes, depth, offset), (32, 32, 1, 32, 22))
        self.assertEqual(size, len(icon) - offset)
        self.assertEqual(icon[offset:offset + 8], b"\x89PNG\r\n\x1a\n")


if __name__ == "__main__":
    unittest.main()
