import unittest

from pycommander.i18n import get_language, set_language, tr_for_language, tr
from pycommander.settingspreview import column_sample_rows


class SettingsPreviewTests(unittest.TestCase):
    def test_syntax_language_placeholder_does_not_collide_with_locale(self):
        before = get_language()
        try:
            for locale in ('en','zh_TW','zh_CN','ko'):
                set_language(locale)
                self.assertIn('YAML', tr('{language} syntax', language='YAML'))
                self.assertIn('Python', tr_for_language(locale, '{language} syntax', language='Python'))
        finally:
            set_language(before)

    def values(self):
        return dict(show_hidden=False, show_system=False, show_extensions=True,
                    mix_sorting=False, date_order='ymd', time_style='24')

    def test_demo_rows_use_real_size_and_date_formats(self):
        rows = column_sample_rows(self.values())
        self.assertEqual(rows[0]['name'], 'Projects')
        self.assertEqual(len(rows), 4)
        self.assertEqual({r['size'] for r in rows}, {'<DIR>', '2 kB', '2 GB', '3 TB'})
        self.assertEqual({r['modified'] for r in rows}, {'2026/09/22 17:15'})

    def test_hidden_system_extension_and_mixed_sort_are_independent(self):
        values = self.values()
        values.update(show_hidden=True, show_system=True, show_extensions=False, mix_sorting=True)
        rows = column_sample_rows(values)
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[0]['name'], '.draft')
        self.assertEqual(next(r['ext'] for r in rows if r['name']=='Notes'), 'MD')
        values['show_hidden'] = False
        rows = column_sample_rows(values)
        self.assertEqual(len(rows), 5)
        self.assertIn('system', {r['visibility'] for r in rows})

    def test_date_sample_matches_twelve_hour_and_date_only_modes(self):
        values = self.values(); values.update(date_order='mdy', time_style='12')
        self.assertEqual(column_sample_rows(values)[0]['modified'], '09/22/2026 0515p')
        values['time_style'] = 'none'
        self.assertEqual(column_sample_rows(values)[0]['modified'], '09/22/2026')

    def test_draft_language_translation_does_not_change_running_language(self):
        before = get_language()
        try:
            set_language('en')
            self.assertEqual(tr_for_language('zh_TW','Files'), '檔案')
            self.assertEqual(tr_for_language('zh_CN','Files'), '文件')
            self.assertEqual(tr_for_language('ko','Files'), '파일')
            self.assertEqual(tr_for_language('zh_TW','Open'), '開啟')
            self.assertEqual(tr_for_language('zh_TW','Properties'), '內容')
            self.assertEqual(get_language(), 'en')
            self.assertEqual(tr_for_language('unknown','Files'), 'Files')
        finally:
            set_language(before)


if __name__=='__main__': unittest.main()
