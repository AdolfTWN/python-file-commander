import configparser
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pycommander.app import ensure_config_defaults, write_config_atomic


class ConfigTests(unittest.TestCase):
    def test_default_ini_is_created_with_safe_operation_defaults(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "pfc.ini"
            config = configparser.ConfigParser(); ensure_config_defaults(config)
            write_config_atomic(config, path)
            restored = configparser.ConfigParser(); restored.read(path, encoding="utf-8")
            self.assertTrue(restored.getboolean("operations", "send_delete_to_recycle_bin"))
            self.assertTrue(restored.getboolean("operations", "continue_after_error"))
            self.assertEqual(restored.get("navigation", "favorites"), "[]")
            self.assertEqual(restored.get("navigation", "recent_folders"), "[]")
            self.assertEqual(restored.getint("view", "panel_count"), 2)
            self.assertEqual(restored.get("view", "ui_language"), "en")
            self.assertEqual(restored.get("view", "color_scheme"), "light")

    def test_existing_preferences_are_not_overwritten(self):
        config = configparser.ConfigParser()
        config.read_dict({"operations": {"send_delete_to_recycle_bin": "false"}})
        ensure_config_defaults(config)
        self.assertFalse(config.getboolean("operations", "send_delete_to_recycle_bin"))

    def test_interrupted_replace_preserves_existing_ini(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "pfc.ini"; path.write_text("[state]\nvalue = old\n", encoding="utf-8")
            config = configparser.ConfigParser(); config.read_dict({"state": {"value": "new"}})
            with mock.patch.object(Path, "replace", side_effect=OSError("simulated interruption")):
                with self.assertRaises(OSError): write_config_atomic(config, path)
            self.assertIn("value = old", path.read_text(encoding="utf-8"))
            self.assertFalse(path.with_suffix(".ini.tmp").exists())


if __name__ == "__main__":
    unittest.main()
