import os
import sys
from pathlib import Path
from unittest.mock import MagicMock
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
sys.path.append(str(Path(__file__).parent.parent.parent))

from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication
from rk7_pro.main import MainWindow
from rk7_pro.components.customization_dialog import CustomizationDialog
from rk7_pro.components.icons import VectorIcon
from rk7_pro.components.phosphor_picker import PhosphorPickerDialog
from rk7_pro.components.phosphor_icons import available_phosphor_names, phosphor_path
from rk7_pro.theme_manager import theme_color


class InterfaceSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def test_navigation_exposes_all_workspaces(self):
        self.assertEqual(
            set(self.window.sidebar.nav_items),
            {"LAUNCH", "GHI ISSUE", "SETTINGS"},
        )
        self.assertNotIn("FOLDERS", self.window.sidebar.nav_items)
        self.window.sidebar.nav_items["SETTINGS"].click()
        self.app.processEvents()
        self.assertEqual(self.window.stack.currentIndex(), 1)

    def test_card_and_icons_emit_exactly_one_action(self):
        panel = self.window.cluster_list
        panel.cluster_selected.disconnect(self.window._on_cluster_selected)
        panel.folder_clicked.disconnect(self.window._on_folder_clicked)
        panel.ini_clicked.disconnect(self.window._on_ini_clicked)
        panel.pin_toggled.disconnect(self.window._on_pin_toggled)
        panel.customization_requested.disconnect(self.window._on_customization_requested)

        card = panel.cards[0]
        spies = {
            "card": QSignalSpy(card.clicked),
            "folder": QSignalSpy(card.folder_clicked),
            "ini": QSignalSpy(card.ini_clicked),
            "pin": QSignalSpy(card.pin_toggled),
            "customize": QSignalSpy(card.customization_requested),
        }

        QTest.mouseClick(card, Qt.MouseButton.LeftButton)
        QTest.mouseClick(card.folder_btn, Qt.MouseButton.LeftButton)
        QTest.mouseClick(card.ini_btn, Qt.MouseButton.LeftButton)
        QTest.mouseClick(card.star_btn, Qt.MouseButton.LeftButton)
        QTest.mouseClick(card.edit_card_btn, Qt.MouseButton.LeftButton)
        self.app.processEvents()

        for spy in spies.values():
            self.assertEqual(spy.count(), 1)

    def test_launch_is_debounced(self):
        state_id = self.window.cluster_list.cards[0].state_id
        self.window.launch_service.launch = MagicMock(return_value=True)
        self.window._last_action_key = None
        self.window._on_cluster_selected(state_id)
        self.window._on_cluster_selected(state_id)
        self.window.launch_service.launch.assert_called_once_with(state_id)

    def test_switching_to_launch_never_creates_card_windows(self):
        for _ in range(3):
            self.window.sidebar.nav_items["SETTINGS"].click()
            self.app.processEvents()
            self.window.sidebar.nav_items["LAUNCH"].click()
            self.app.processEvents()

            for card in self.window.cluster_list.cards:
                self.assertIs(card.parentWidget(), self.window.cluster_list.grid_widget)
                self.assertFalse(card.isWindow())

    def test_grid_reflows_at_supported_widths(self):
        self.assertEqual(
            self.window.cluster_list.grid_layout.count(),
            len(self.window.cluster_list.cards),
        )
        self.assertGreater(self.window.cluster_list.grid_layout.count(), 0)
        self.assertFalse(hasattr(self.window, "list_btn"))
        self.assertFalse(hasattr(self.window, "grid_btn"))

        self.window.resize(1024, 680)
        self.app.processEvents()
        self.assertEqual(self.window.cluster_list.columns, 2)

        self.window.resize(1200, 760)
        self.app.processEvents()
        self.assertEqual(self.window.cluster_list.columns, 2)

        self.window.resize(1440, 860)
        self.app.processEvents()
        self.assertEqual(self.window.cluster_list.columns, 3)

        first_card = self.window.cluster_list.cards[0]
        self.assertFalse(hasattr(first_card, "sub_lbl"))
        self.assertEqual(first_card.maximumHeight(), 246)
        self.assertTrue(hasattr(first_card, "path_lbl"))
        animated_actions = [
            first_card.folder_btn,
            first_card.ini_btn,
            first_card.star_btn,
            first_card.edit_card_btn,
        ]
        for button in animated_actions:
            self.assertEqual(button.width(), 36)
            button.set_hover_progress(1.0)
            self.assertEqual(button.get_hover_progress(), 1.0)
        first_card.star_btn.set_active(True)
        self.assertTrue(first_card.star_btn.active)

        first_card.set_card_hover_progress(1.0)
        self.assertEqual(first_card.get_card_hover_progress(), 1.0)
        self.assertEqual(first_card.shadow.blurRadius(), 18.0)
        first_card.set_card_hover_progress(0.0)
        self.assertFalse(self.window.header.avatar_btn.isVisible())
        self.assertFalse(self.window.refresh_btn.isVisible())
        self.assertFalse(self.window.sidebar.status_card.isVisible())
        self.assertFalse(hasattr(first_card, "launch_btn"))

        self.window.refresh_btn.click()
        self.app.processEvents()
        self.assertEqual(
            self.window.header.subtitle_lbl.text(),
            "Library updated just now",
        )
    def test_status_filters_and_metrics(self):
        cards = self.window.cluster_list.cards
        pinned_count = sum(1 for card in cards if card.is_pinned)
        running_count = sum(1 for card in cards if card.is_active)
        self.assertEqual(self.window.header.total_metric.value_lbl.text(), str(len(cards)))
        self.assertEqual(self.window.header.pinned_metric.value_lbl.text(), str(pinned_count))
        self.assertEqual(self.window.header.running_metric.value_lbl.text(), str(running_count))

        self.window.pinned_filter_btn.click()
        self.app.processEvents()
        self.assertEqual(self.window.cluster_list.grid_layout.count(), pinned_count)
        self.assertTrue(self.window.pinned_filter_btn.isChecked())

        self.window.running_filter_btn.click()
        self.app.processEvents()
        self.assertEqual(self.window.cluster_list.grid_layout.count(), running_count)
        self.assertTrue(self.window.running_filter_btn.isChecked())

        self.window.all_filter_btn.click()
        self.app.processEvents()
        self.assertEqual(self.window.cluster_list.grid_layout.count(), len(cards))

    def test_search_empty_state_and_count(self):
        self.window.search_bar.input_field.setText("__no_shortcut_matches__")
        self.window._exec_search()
        self.assertTrue(self.window.cluster_list.empty_state.isVisible())
        self.assertTrue(self.window.cluster_list.count_lbl.text().startswith("0 OF"))

    def test_theme_toggle_switches_light_and_dark_surfaces(self):
        self.window._set_dark_mode(False, persist=False)
        original_icon_colors = [
            icon.color.upper() for icon in self.window.findChildren(VectorIcon)
        ]
        self.window._save_setting = MagicMock()
        self.window.header.theme_toggle.click()
        self.app.processEvents()
        self.assertTrue(self.window.dark_mode)
        self.assertTrue(self.window.header.theme_toggle.isChecked())
        self.window._save_setting.assert_called_once_with("theme", "dark")
        self.assertIn("#0F172A", self.window.centralWidget().styleSheet().upper())
        self.assertIn("#111827", self.window.header.total_metric.styleSheet().upper())

        card = self.window.cluster_list.cards[0]
        card.set_selected(False)
        for button in (card.folder_btn, card.ini_btn, card.edit_card_btn):
            button.set_hover_progress(1.0)
            button.set_hover_progress(0.0)
        self.app.processEvents()
        self.assertIn("BACKGROUND: TRANSPARENT", card.styleSheet().upper())
        self.assertEqual(theme_color("#FFFFFF"), "#111827")

        self.window._save_setting.reset_mock()
        self.window.header.theme_toggle.click()
        self.app.processEvents()
        self.assertFalse(self.window.dark_mode)
        self.assertFalse(self.window.header.theme_toggle.isChecked())
        self.assertIn("#F4F7FB", self.window.centralWidget().styleSheet().upper())
        restored_icon_colors = [
            icon.color.upper() for icon in self.window.findChildren(VectorIcon)
        ]
        self.assertEqual(restored_icon_colors, original_icon_colors)
        self.window._save_setting.assert_called_once_with("theme", "light")
    def test_customization_icon_picker_updates_card_identity(self):
        dialog = CustomizationDialog("Demo", "#2563EB", None, None, self.window)
        self.assertEqual(len(dialog.icon_btns), 9)
        dialog._select_icon("coffee")
        self.assertEqual(dialog.get_values(), ("Demo", "#2563EB", "coffee", None))

        card = self.window.cluster_list.cards[0]
        card.update_info(
            card._full_subtitle, card.is_pinned, card.is_active,
            custom_name=card.custom_name, custom_color=card.custom_color,
            custom_icon="coffee",
        )
        self.assertEqual(card.avatar_icon.icon_name, "coffee")
        self.assertTrue(card.avatar_icon.isVisible())
        self.assertFalse(card.avatar_lbl.isVisible())

    def test_phosphor_library_search_and_selection(self):
        self.assertEqual(len(available_phosphor_names("regular")), 1512)
        self.assertIsNotNone(phosphor_path("phosphor:bold:folder-open"))
        picker = PhosphorPickerDialog(parent=self.window)
        picker.search_input.setText("coffee")
        picker._refresh_grid()
        self.assertGreaterEqual(len(picker._buttons), 2)
        picker._buttons[0].click()
        self.assertTrue(picker.get_icon().startswith("phosphor:light:coffee"))
        picker.close()

    def test_editor_cancel_restores_original_content(self):
        editor = self.window.editor_panel
        editor.load_content("sample.ini", "[main]\nkey=value")
        editor._toggle_edit()
        editor.editor.setPlainText("[main]\nkey=changed")
        editor._toggle_edit()
        self.assertEqual(editor.editor.toPlainText(), "[main]\nkey=value")
        self.assertTrue(editor.editor.isReadOnly())


if __name__ == "__main__":
    unittest.main()
