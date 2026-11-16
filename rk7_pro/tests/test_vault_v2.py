import tempfile
import base64
import json
import unittest
from pathlib import Path

from rk7_pro.core.script_repository import ScriptRepository
from rk7_pro.core.vault_files import VaultFiles
from web_bridge import WebBridgeAPI


class VaultV2Tests(unittest.TestCase):
    def test_safe_save_preserves_utf8_bom_and_crlf_and_rejects_external_change(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            path = root / "query.sql"
            path.write_bytes(b"\xef\xbb\xbfSELECT 1;\r\nGO\r\n")
            files = VaultFiles(root)
            original = files.read(path)
            self.assertEqual(original["encoding"], "utf-8-sig")
            self.assertEqual(original["newline"], "\r\n")
            files.save_draft(path, "SELECT 2;\nGO\n", original["hash"])
            self.assertEqual(path.read_bytes(), b"\xef\xbb\xbfSELECT 1;\r\nGO\r\n")
            saved = files.write(path, "SELECT 2;\nGO\n", original["hash"], original["encoding"], original["newline"])
            self.assertEqual(path.read_bytes(), b"\xef\xbb\xbfSELECT 2;\r\nGO\r\n")
            path.write_text("changed elsewhere", encoding="utf-8")
            with self.assertRaises(ValueError):
                files.write(path, "overwrite", saved["hash"], "utf-8")
            self.assertEqual(path.read_text(encoding="utf-8"), "changed elsewhere")

    def test_same_named_files_keep_separate_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "A").mkdir()
            (root / "B").mkdir()
            (root / "A" / "query.sql").write_text("SELECT 1", encoding="utf-8")
            (root / "B" / "query.sql").write_text("SELECT 2", encoding="utf-8")
            repo = ScriptRepository(directory)
            repo.scan()
            first = next(s for s in repo.snippets if s.file_path.parent.name == "A")
            second = next(s for s in repo.snippets if s.file_path.parent.name == "B")
            repo.toggle_favorite(first)
            repo.scan()
            self.assertTrue(next(s for s in repo.snippets if s.file_path.parent.name == "A").is_favorite)
            self.assertFalse(next(s for s in repo.snippets if s.file_path.parent.name == "B").is_favorite)

    def test_legacy_filename_metadata_is_read_and_preserved(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            (root / "query.sql").write_bytes(b"SELECT 1")
            (root / ".vault_meta.json").write_text(json.dumps({"query.sql": {"description": "Existing note", "tags": ["#OLD"]}}), encoding="utf-8")
            repo = ScriptRepository(directory)
            script = repo.scan()[0]
            self.assertEqual(script.description, "Existing note")
            repo.toggle_favorite(script)
            repo.scan()
            self.assertEqual(repo.snippets[0].tags, ["#OLD"])
            self.assertTrue(repo.snippets[0].is_favorite)

    def test_duplicate_and_trash_preserve_original(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            source = root / "query.sql"
            source.write_text("SELECT 1", encoding="utf-8")
            files = VaultFiles(root)
            copy = Path(files.duplicate(source, "query copy.sql"))
            self.assertEqual(copy.read_bytes(), source.read_bytes())
            with self.assertRaises(FileExistsError):
                files.duplicate(source, "query copy.sql")
            renamed = Path(files.rename(copy, "query final.sql"))
            self.assertFalse(copy.exists())
            self.assertEqual(renamed.read_bytes(), source.read_bytes())
            trash = Path(files.delete_to_trash(renamed))
            self.assertTrue(trash.is_file())
            self.assertTrue(source.is_file())

    def test_bridge_lists_without_content_and_opens_on_demand(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            path = root / "query.sql"
            path.write_bytes(b"SELECT 1;\n")
            api = WebBridgeAPI.__new__(WebBridgeAPI)
            api.script_repo = ScriptRepository(directory)
            listed = api.get_scripts()
            self.assertEqual(len(listed), 1)
            self.assertNotIn("content", listed[0])
            opened = api.get_script(str(path))
            self.assertTrue(opened["success"])
            self.assertEqual(opened["content"], "SELECT 1;\n")
            saved = api.save_script(str(path), "SELECT 2;\n", opened["hash"], opened["encoding"], opened["newline"])
            self.assertTrue(saved["success"])
            self.assertEqual(path.read_bytes(), b"SELECT 2;\n")

    def test_import_collision_options_and_replace_backup(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            vault = root / "vault"
            vault.mkdir()
            source = root / "query.sql"
            source.write_bytes(b"SELECT 2")
            existing = vault / "query.sql"
            existing.write_bytes(b"SELECT 1")
            repo = ScriptRepository(str(vault))
            self.assertEqual(repo.import_files([source], "skip"), 0)
            self.assertEqual(existing.read_bytes(), b"SELECT 1")
            self.assertEqual(repo.import_files([source], "rename"), 1)
            self.assertEqual((vault / "query (2).sql").read_bytes(), b"SELECT 2")
            self.assertEqual(repo.import_files([source], "replace"), 1)
            self.assertEqual(existing.read_bytes(), b"SELECT 2")
            self.assertTrue(list((vault / ".rk7_vault_backups").glob("*__query.sql")))

    def test_drag_import_keeps_existing_file_until_replace_selected(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            target = root / "query.sql"
            target.write_bytes(b"SELECT 1")
            api = WebBridgeAPI.__new__(WebBridgeAPI)
            api.script_repo = ScriptRepository(directory)
            item = {"name": "query.sql", "base64": base64.b64encode(b"SELECT 2").decode()}
            self.assertEqual(api.import_script_blobs([item], "skip")["skipped"], 1)
            self.assertEqual(target.read_bytes(), b"SELECT 1")
            self.assertEqual(api.import_script_blobs([item], "replace")["count"], 1)
            self.assertEqual(target.read_bytes(), b"SELECT 2")
            self.assertTrue(list((root / ".rk7_vault_backups").glob("*__query.sql")))


if __name__ == "__main__":
    unittest.main()
