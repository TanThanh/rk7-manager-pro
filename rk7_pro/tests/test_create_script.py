import tempfile
import unittest
from pathlib import Path

from rk7_pro.core.script_repository import ScriptRepository


class CreateScriptTests(unittest.TestCase):
    def test_creates_sql_in_selected_folder_without_overwriting(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "Queries").mkdir()
            repo = ScriptRepository(str(root))

            snippet = repo.create_script("Check sales.sql", "SQL", "Queries", "SELECT 1;\n")
            target = root / "Queries" / "Check sales.sql"
            self.assertEqual(snippet.file_path, target)
            self.assertEqual(snippet.file_type, "SQL")
            self.assertEqual(target.read_text(encoding="utf-8"), "SELECT 1;\n")
            self.assertEqual([item.filename for item in repo.scan() if item.file_path == target], [target.name])

            with self.assertRaises(FileExistsError):
                repo.create_script("Check sales", "SQL", "Queries", "SELECT 2;")
            self.assertEqual(target.read_text(encoding="utf-8"), "SELECT 1;\n")

    def test_rejects_invalid_names_and_folders(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = ScriptRepository(temporary)
            for name in ("../outside", "CON", "bad:name"):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    repo.create_script(name, "SQL", "", "")
            with self.assertRaises(ValueError):
                repo.create_script("safe", "SQL", "../outside", "")


if __name__ == "__main__":
    unittest.main()
