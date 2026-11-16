import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from rk7_pro.core.models import ShortcutState
from web_bridge import WebBridgeAPI


class ShortcutDetailsTests(unittest.TestCase):
    def make_api(self, root):
        api = WebBridgeAPI.__new__(WebBridgeAPI)
        api.base_dir = root
        api.card_backgrounds_dir = root / "rk7_pro" / "card_backgrounds"
        api.customization_file = root / "rk7_pro" / "customization.json"
        api.customization_file.parent.mkdir()
        api.launch_history_file = root / "rk7_pro" / "launch_history.json"
        api.launch_history = {}
        api._launch_history_lock = threading.Lock()
        api.shortcut_dir = root
        api._window = MagicMock()
        exe = root / "app.exe"
        exe.write_bytes(b"example")
        api.states = {
            "first.lnk": ShortcutState("first.lnk", "First", target_exe_path=str(exe)),
            "second.lnk": ShortcutState("second.lnk", "Second", target_exe_path=str(exe)),
        }
        api._broadcast_state_change = MagicMock()
        return api

    def test_launch_counts_are_independent_and_persisted(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            api = self.make_api(Path(directory))
            with patch("web_bridge.subprocess.Popen", return_value=MagicMock(pid=123)):
                self.assertTrue(api.launch_shortcut("first.lnk")["success"])
                self.assertTrue(api.launch_shortcut("first.lnk")["success"])
                self.assertTrue(api.launch_shortcut("second.lnk")["success"])
            self.assertEqual(api._load_launch_history()["first.lnk"]["count"], 2)
            self.assertEqual(api._load_launch_history()["second.lnk"]["count"], 1)
            shortcuts = {item["id"]: item for item in api.get_shortcuts()}
            self.assertEqual(shortcuts["first.lnk"]["launch_count"], 2)
            self.assertEqual(shortcuts["second.lnk"]["launch_count"], 1)

    def test_background_can_be_selected_and_removed(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            api = self.make_api(root)
            source = root / "image.png"
            Image.new("RGB", (20, 20), "blue").save(source)
            api._window.create_file_dialog.return_value = [str(source)]
            result = api.pick_shortcut_background("first.lnk")
            self.assertTrue(result["success"])
            self.assertTrue(result["custom_background"].startswith("data:image/png;base64,"))
            self.assertEqual(api.get_shortcuts()[0]["custom_background"], result["custom_background"])
            self.assertTrue(api._load_customizations()["first.lnk"]["background"].startswith("card_backgrounds/"))
            self.assertTrue(api.clear_shortcut_background("first.lnk")["success"])
            self.assertIsNone(api.states["first.lnk"].custom_background)
            self.assertNotIn("first.lnk", api._load_customizations())


if __name__ == "__main__":
    unittest.main()
