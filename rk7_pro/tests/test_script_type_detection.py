import tempfile
import unittest
from pathlib import Path

from rk7_pro.core.script_repository import ScriptRepository


class ScriptTypeDetectionTests(unittest.TestCase):
    def test_text_extension_sql_is_imported_and_classified(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "query.text"
            source.write_text(
                "-- Report\nUSE [RK7];\nGO\n/* Query */\nSELECT ID FROM ORDERS;\n",
                encoding="utf-8",
            )
            repo = ScriptRepository(str(Path(root) / "vault"))
            self.assertEqual(repo.import_files([source]), 1)
            snippet = next(s for s in repo.snippets if s.filename == source.name)
            self.assertEqual(snippet.file_type, "SQL")
            self.assertIn("#SQL", snippet.tags)

    def test_plain_text_stays_text_and_updates_after_edit(self):
        with tempfile.TemporaryDirectory() as root:
            vault = Path(root) / "vault"
            vault.mkdir()
            source = vault / "notes.txt"
            source.write_text("Deployment notes for the team.\n", encoding="utf-8")
            repo = ScriptRepository(str(vault))
            snippet = repo.scan()[0]
            self.assertEqual(snippet.file_type, "Text")
            self.assertTrue(snippet.save_content("DECLARE @id int;\nSELECT @id;\n"))
            self.assertEqual(snippet.file_type, "SQL")


if __name__ == "__main__":
    unittest.main()
