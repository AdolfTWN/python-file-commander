import unittest

from pycommander.app import middle_ellipsize


class NameDisplayTests(unittest.TestCase):
    def test_middle_ellipsis_preserves_name_start_and_extension(self):
        text = "ABCDEFGHIJKLMN123456789123.txt"
        shortened = middle_ellipsize(text, 22, len)
        self.assertLessEqual(len(shortened), 22)
        self.assertTrue(shortened.startswith("ABCDEFG"))
        self.assertTrue(shortened.endswith(".txt"))
        self.assertIn("...", shortened)

    def test_short_name_is_unchanged(self):
        self.assertEqual(middle_ellipsize("report.txt", 40, len), "report.txt")

    def test_release_identifier_survives_middle_ellipsis(self):
        first = middle_ellipsize("UVIP_123_product_catalog_validated_package.zip", 30, len)
        second = middle_ellipsize("UVIP_456_product_catalog_validated_package.zip", 30, len)
        self.assertIn("123", first)
        self.assertIn("456", second)
        self.assertNotEqual(first, second)
        self.assertTrue(first.startswith("UVIP"))
        self.assertTrue(first.endswith("package.zip"))

    def test_multi_part_version_survives_middle_ellipsis(self):
        shortened = middle_ellipsize(
            "UVIP_E2E_Navigator_v1.9.0_R4.6_FLAT_PRODUCT_TYPE_CATALOG_PACKAGE.zip", 38, len)
        self.assertIn("v1.9.0", shortened)
        self.assertIn("R4.6", shortened)


if __name__ == "__main__":
    unittest.main()
