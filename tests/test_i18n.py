import unittest

from pycommander.i18n import LANGUAGES, set_language, tr


class TranslationTests(unittest.TestCase):
    def tearDown(self):
        set_language("en")

    def test_supported_languages_and_english_fallback(self):
        self.assertEqual([code for code, _label in LANGUAGES], ["en", "zh_TW", "zh_CN", "ko"])
        set_language("unknown")
        self.assertEqual(tr("Files"), "Files")

    def test_file_manager_terms_use_native_conventions(self):
        expected = {
            "zh_TW": ("檔案", "資料夾", "資源回收筒", "批次重新命名"),
            "zh_CN": ("文件", "文件夹", "回收站", "批量重命名"),
            "ko": ("파일", "폴더", "휴지통", "일괄 이름 바꾸기"),
        }
        for language, terms in expected.items():
            set_language(language)
            self.assertEqual((tr("Files"), tr("folder"), tr("Recycle Bin"), tr("Multi-Rename")), terms)

    def test_placeholders_are_localized_without_losing_values(self):
        set_language("zh_TW")
        self.assertEqual(tr("{count} Panels", count=4), "4 個面板")
        self.assertIn("10", tr("and {count} more {kind}", count=10, kind=tr("files")))


if __name__ == "__main__":
    unittest.main()
