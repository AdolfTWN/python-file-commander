import configparser
import io
from pathlib import Path, PureWindowsPath as W, PurePosixPath as P
import unittest
import struct
import zlib
from unittest.mock import patch

from pycommander.homeprefix import load_custom_prefixes, save_custom_prefixes, match_home_prefix, discover_home_prefixes, prefix_icon_png, PREFIX_ICONS


class HomePrefixTests(unittest.TestCase):
    def test_icons_are_distinct_native_size_and_antialiased(self):
        for size in (16, 32, 64):
            rendered = []
            for kind in ('parent', *PREFIX_ICONS):
                png = prefix_icon_png(kind, size)
                self.assertEqual(struct.unpack('>II', png[16:24]), (size,size))
                offset, compressed = 8, bytearray()
                while offset < len(png):
                    length = struct.unpack('>I', png[offset:offset+4])[0]
                    if png[offset+4:offset+8] == b'IDAT': compressed.extend(png[offset+8:offset+8+length])
                    offset += length+12
                raw = zlib.decompress(compressed); stride = size*4+1
                alphas = [raw[y*stride+1+x*4+3] for y in range(size) for x in range(size)]
                self.assertIn(0, alphas); self.assertIn(255, alphas)
                self.assertTrue(any(0<a<255 for a in alphas), kind)
                rendered.append(png)
            self.assertEqual(len(set(rendered)), 7)

    def test_longest_and_component_boundary(self):
        auto = [(W('C:/Users/A'), 'home'), (W('C:/Users/A/OneDrive - Work'), 'cloud'),
                (W('D:/Downloads'), 'download')]
        self.assertEqual(match_home_prefix(W('c:/users/a/onedrive - work/Code'), auto, [])[1], 'cloud')
        self.assertIsNone(match_home_prefix(W('C:/Users/AB'), auto, []))
        self.assertEqual(match_home_prefix(W('d:/downloads/a'), auto, [])[1], 'download')
        self.assertIsNone(match_home_prefix(W('D:/Downloads-old'), auto, []))
        custom = [{'path': 'C:/Users/A/OneDrive - Work/Code', 'icon': 'code'}]
        self.assertEqual(match_home_prefix(W('C:/Users/A/OneDrive - Work/Code/a.zip'), auto, custom)[1], 'code')

    def test_unc_and_custom_tie(self):
        path = W('//server/share/Folder/sub')
        auto = [(W('//server/share/Folder'), 'home')]
        custom = [{'path': '//SERVER/share/Folder', 'icon': 'photos'}]
        self.assertEqual(match_home_prefix(path, auto, custom)[1], 'photos')
        self.assertIsNone(match_home_prefix(W('//server/share/Folder2'), auto, custom))

    def test_ini_roundtrip_unicode_and_percent(self):
        config = configparser.ConfigParser()
        items = [{'icon': 'code', 'path': '/程式/100% ready'}, {'icon': 'documents', 'path': ''},
                 {'icon': 'photos', 'path': '//server/share/pictures'}]
        save_custom_prefixes(config, items)
        stream = io.StringIO(); config.write(stream)
        restored = configparser.ConfigParser(); restored.read_string(stream.getvalue())
        self.assertEqual(load_custom_prefixes(restored), items)

    def test_malformed_preferences(self):
        config = configparser.ConfigParser(); config.add_section('home_prefixes')
        for raw in ('bad', '{}', '[{"icon":[],"path":7}]', '[null]'):
            config.set('home_prefixes', 'custom', raw)
            self.assertEqual(load_custom_prefixes(config)[0], {'icon': 'code', 'path': ''})

    def test_posix_case_sensitive(self):
        self.assertIsNone(match_home_prefix(P('/CODE/sub'), [(P('/Code'), 'code')], []))

    def test_env_multiple_onedrives(self):
        personal, work = Path.home() / 'CloudPersonal', Path.home() / 'CloudWork'
        with patch.dict('os.environ', {'OneDriveConsumer': str(personal), 'OneDriveCommercial': str(work)}):
            values = discover_home_prefixes()
        self.assertIn((personal, 'cloud'), values)
        self.assertIn((work, 'cloud'), values)
