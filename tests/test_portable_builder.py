import ast
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import build_single_file as builder


class PortableBuilderTests(unittest.TestCase):
    def test_manifest_includes_every_application_module_exactly_once(self):
        modules = {p.stem for p in (builder.ROOT / "pycommander").glob("*.py")}
        self.assertEqual(set(builder.MODULES), modules - {"__init__", "__main__"})
        self.assertEqual(len(builder.MODULES), len(set(builder.MODULES)))

    def test_multiline_imports_removed_without_discarding_following_code(self):
        source = 'from __future__ import annotations\nfrom .sample import (\n    first,\n    second,\n)\nresult = first + second\n'
        tree = ast.parse(builder.flatten_source(source, "sample.py"))
        self.assertEqual(len(tree.body), 1)
        self.assertIsInstance(tree.body[0], ast.Assign)

    def test_strings_comments_and_nested_fallback_imports_preserved(self):
        source = 'text = "from .module import name"\n# from .module import name\ndef worker():\n    from .i18n import set_language as locale\n    return locale\n'
        self.assertEqual(ast.dump(ast.parse(builder.flatten_source(source, "sample.py"))),
                         ast.dump(ast.parse(source)))

    def test_unsupported_imports_fail_explicitly(self):
        for source in ("from .module import name as other\n", "from .module import *\n",
                       "from ..module import name\n", "from __future__ import division\n",
                       "from .module import name; value = 1\n"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                builder.flatten_source(source, "sample.py")

    def test_source_line_positions_preserved_within_each_fragment(self):
        result = builder.flatten_source('from .module import (\n name,\n)\nvalue = 1\n', "sample.py")
        self.assertEqual(ast.parse(result).body[0].lineno, 4)

    def test_render_deterministic_for_explicit_date_and_contains_no_top_level_relative_import(self):
        first = builder.render(build_date="2026/10/08")
        self.assertEqual(first, builder.render(build_date="2026/10/08"))
        tree = ast.parse(first)
        self.assertFalse(any(isinstance(n, ast.ImportFrom) and n.level for n in tree.body))
        self.assertEqual(sum(isinstance(n, ast.ImportFrom) and n.module == "__future__"
                             for n in tree.body), 1)
        self.assertEqual(first.count("# Source: pycommander/"), len(builder.MODULES))

    def test_rendered_portable_matches_checked_in_artifact(self):
        source = (builder.ROOT / "pfc.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        date = next(n.value.value for n in tree.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "BUILD_DATE" for t in n.targets))
        self.assertEqual(source, builder.render(build_date=date))

    def test_invalid_source_never_replaces_existing_artifact(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "pfc.py").write_text("working artifact", encoding="utf-8")
            with patch.object(builder, "ROOT", root), patch.object(builder, "render", side_effect=SyntaxError):
                with self.assertRaises(SyntaxError):
                    builder.build()
            self.assertEqual((root / "pfc.py").read_text(), "working artifact")


if __name__ == "__main__":
    unittest.main()
