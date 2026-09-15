import unittest
from pathlib import PurePosixPath, PureWindowsPath
from pycommander.pathbar import fit_crumbs, path_ancestors


class PathBarTests(unittest.TestCase):
    def test_windows_and_unc_targets(self):
        for path in (PureWindowsPath('C:/Projects/Documents'),
                     PureWindowsPath('//server/share/中文/Documents'), PurePosixPath('/a/b')):
            parts = path_ancestors(path)
            self.assertEqual(parts[-1][1], path)
            self.assertEqual(parts[0][1], path.parents[-1])

    def test_fit_keeps_tail_and_target_indices(self):
        parts = path_ancestors(PurePosixPath('/one/two/Documents'))
        for width in (20, 70, 130, 1000):
            fitted = fit_crumbs(parts, width, lambda s: len(s) * 8)
            self.assertEqual(fitted[-1][1], len(parts) - 1)
            self.assertLessEqual(sum(item[2] for item in fitted), width)
        self.assertEqual([i for _, i, _ in fit_crumbs(parts, 1000, len)], list(range(len(parts))))

    def test_long_current_name(self):
        parts = [('文件' * 100, '/target')]
        result = fit_crumbs(parts, 140, lambda s: len(s) * 10)
        self.assertIn('…', result[0][0])
        self.assertEqual(result[0][1], 0)
        self.assertLessEqual(len(result[0][0]) * 10, 120)
